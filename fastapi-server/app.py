from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Dict, List, Set
import json
from datetime import datetime
import uuid
import asyncio
import time
from deepagents.backends import FilesystemBackend


from playwright.async_api import async_playwright

from deepagents import create_deep_agent
from browser_tools_revised import build_tools


from pydantic import BaseModel, Field
from typing import Optional

import os
from browser_session_handler import BrowserSession

from config import get_models, get_model_list
from prompts.deep_agent import prompt
import db

llm = None
llm_deterministic = None

project_dir = None

agent_interrupted = False
GOOGLE_CHROME_PATH = os.environ.get("GOOGLE_CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
headless_mode = os.environ.get("HEADLESS", "false").lower() == "true"
app = FastAPI(title="AI Agent WebSocket Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# SETTINGS (SQLite persistence)
# -------------------------------
@app.get("/api/settings")
async def get_settings():
    return {
        "api_key": db.get_setting("api_key") or "",
        "model_name": db.get_setting("model_name") or "deepseek-v4-flash",
        "project_dir": db.get_setting("project_dir") or "",
        "headless": db.get_setting("headless") == "true",
    }

@app.post("/api/settings")
async def save_settings(request: Request):
    body = await request.json()
    if "api_key" in body:
        db.set_setting("api_key", body["api_key"])
    if "model_name" in body:
        db.set_setting("model_name", body["model_name"])
    if "project_dir" in body:
        db.set_setting("project_dir", body["project_dir"])
    if "headless" in body:
        db.set_setting("headless", "true" if body["headless"] else "false")
    return {"ok": True}

@app.get("/api/models")
async def list_models():
    return {"models": get_model_list()}

# -------------------------------
# DATA STRUCTURES
# -------------------------------
class QueryRouterResponse(BaseModel):
    browsing_required: bool
    response: Optional[str] = Field(None, description="Response")

class ChatManager:
    def __init__(self):
        self.chat_histories: Dict[str, List[dict]] = {}
    
    def get_chat_history(self, session_id: str) -> List[dict]:
        if session_id not in self.chat_histories:
            self.chat_histories[session_id] = []
        return self.chat_histories[session_id]
    
    def update_chat_history(self, message: dict, session_id: str):
        if session_id not in self.chat_histories:
            self.chat_histories[session_id] = []
        self.chat_histories[session_id].append(message)
    
    def clear_history(self, session_id: str):
        if session_id in self.chat_histories:
            self.chat_histories[session_id] = []

chat_manager = ChatManager()

# Store pending user input requests
pending_inputs: Dict[str, asyncio.Future] = {}

# Track active WebSocket connections and their status
active_connections: Dict[str, WebSocket] = {}
connection_tasks: Dict[str, Set[asyncio.Task]] = {}

# Extracted file content waiting to be included in next message
pending_file_contents: Dict[str, List[dict]] = {}

def extract_file_content(file_path: str, filename: str) -> str:
    """Extract text content from an uploaded file."""
    ext = os.path.splitext(filename)[1].lower()

    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages)

        elif ext in (".csv", ".tsv"):
            import csv
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                rows = list(reader)
            return "\n".join([",".join(row) for row in rows[:500]])

        elif ext in (".json", ".jsonl"):
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return content[:50000]

        elif ext in (".txt", ".md", ".log", ".xml", ".html",
                      ".yaml", ".yml", ".toml", ".cfg", ".conf", ".ini"):
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()[:50000]

        else:
            return f"[Binary file: {filename} — cannot extract text]"

    except Exception as e:
        return f"[Error reading {filename}: {e}]"

# -------------------------------
# SAFE WEBSOCKET SENDER
# -------------------------------
class SafeWebSocket:
    def __init__(self, websocket: WebSocket, session_id: str):
        self.websocket = websocket
        self.session_id = session_id
        self._closed = False
        self._lock = asyncio.Lock()
        self._on_disconnect = None

    def set_disconnect_handler(self, fn):
        self._on_disconnect = fn

    async def send(self, data: dict) -> bool:
        if self._closed:
            return False

        async with self._lock:
            try:
                await asyncio.wait_for(
                    self.websocket.send_text(json.dumps(data)),
                    timeout=5
                )
                return True

            except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError) as e:
                print(f"[WS CLOSED] {self.session_id}: {e}")
                await self._handle_disconnect()
                return False

            except Exception as e:
                print(f"[WS ERROR] {self.session_id}: {e}")
                await self._handle_disconnect()
                return False

    async def _handle_disconnect(self):
        if not self._closed:
            self._closed = True
            if self._on_disconnect:
                await self._on_disconnect(self.session_id)

    async def replace(self, websocket: WebSocket):
        async with self._lock:
            self.websocket = websocket
            self._closed = False
            print(f"[WS REPLACED] {self.session_id}")

    async def close(self):
        self._closed = True

    @property
    def is_closed(self):
        return self._closed

safe_connections: Dict[str, SafeWebSocket] = {}

# -------------------------------
# HELPER FUNCTIONS
# -------------------------------
async def request_user_input(message: str, safe_ws: SafeWebSocket, input_type: str = "text", options: list = None, fields: list = None) -> str:
    """
    Request input from user and wait for response.
    Returns the user's input as a string.
    """
    request_id = str(uuid.uuid4())
    
    # Create a future to wait for user response
    future = asyncio.Future()
    pending_inputs[request_id] = future
    try:
        allow_input = await safe_ws.send({
            "type" : "processing_request_completed"
        })
    except:
        pass
    try:
        # Send input request to client with UI metadata
        payload = {
            "type": "form_input",
            "request_id": request_id,
            "role": "assistant",
            "content": message,
            "input_type": input_type,
            "timestamp": datetime.now().isoformat(),
        }
        if options:
            payload["options"] = options
        if fields:
            payload["fields"] = fields

        success = await safe_ws.send(payload)
        
        if not success:
            return "WebSocket connection closed"
        
        # Wait for user response (with 5 minute timeout)
        try:
            user_response = await asyncio.wait_for(future, timeout=300.0)
            await safe_ws.send({
                "type": "agent_thinking",
                "timestamp": datetime.now().isoformat(),
            })
            return user_response
        except asyncio.TimeoutError:
            return "User did not respond in time"
    except Exception as e:
        await log_chat(f"Error requesting user input: {e}", safe_ws)
        return f"Error requesting user input: {e}"
    finally:
        # Clean up
        pending_inputs.pop(request_id, None)

async def log_chat(message: str, safe_ws: SafeWebSocket):
    """Send log message to client"""
    # print("Sending Log.")
    await safe_ws.send({
        "type": "log",
        "content": message,
        "timestamp": datetime.now().isoformat(),
    })

def get_user_files_dir():
    base = os.path.join(project_dir, "files")
    os.makedirs(base, exist_ok=True)
    return base


def resolve_user_path(relative_path: str):
    base = get_user_files_dir()
    clean = relative_path.replace("files/", "", 1)
    full_path = os.path.join(base, clean)

    # 🔒 Prevent path traversal
    if not os.path.abspath(full_path).startswith(os.path.abspath(base)):
        raise Exception("Invalid file path (security violation)")

    return full_path

import sys
import os
import shutil as _shutil

def sync_skills_to_project():
    """Copy built-in skills from the codebase to the user's project files directory."""
    skills_source = os.path.join(os.path.dirname(__file__), "skills")
    skills_dest = os.path.join(get_user_files_dir(), "skills", "user")
    if not os.path.isdir(skills_source):
        return
    os.makedirs(skills_dest, exist_ok=True)
    for skill_name in os.listdir(skills_source):
        src = os.path.join(skills_source, skill_name)
        dst = os.path.join(skills_dest, skill_name)
        if os.path.isdir(src):
            _shutil.copytree(src, dst, dirs_exist_ok=True)

def get_resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource (works in dev + PyInstaller)
    """
    if hasattr(sys, '_MEIPASS'):
        # Running from PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # Running in normal Python environment
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def load_prompt(filename: str) -> str:
    path = get_resource_path(f"prompts/{filename}")
    
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
    



async def file_tree_data(safe_ws: SafeWebSocket):
    """
    Get all files and folders inside the user files directory recursively.

    Sends the result to the frontend via WebSocket.
    """

    # await log_chat("Getting full file tree", safe_ws)
    # await log_chat(f"Project dir: {project_dir}", safe_ws)
    try:
        base_dir = get_user_files_dir()
        # await log_chat(f"Base dir: {base_dir}", safe_ws)
        nodes = []

        for root, dirs, files in os.walk(base_dir):

            # ✅ Folders (including empty ones)
            for d in dirs:
                full_path = os.path.join(root, d)

                rel = os.path.relpath(full_path, base_dir)
                project_path = f"files/{rel.replace(os.sep, '/')}"

                nodes.append({
                    "name": d,
                    "path": full_path,
                    "project_path": project_path,
                    "type": "folder"
                })

            # ✅ Files
            for f in files:
                full_path = os.path.join(root, f)

                rel = os.path.relpath(full_path, base_dir)
                project_path = f"files/{rel.replace(os.sep, '/')}"

                nodes.append({
                    "name": f,
                    "path": full_path,
                    "project_path": project_path,
                    "type": "file"
                })

        result = {"nodes": nodes}

        # 🔥 Avoid logging huge payloads
        # await log_chat(f"File tree nodes: {len(nodes)} items", safe_ws)




        # 🔒 Safe send
        if not safe_ws.is_closed:
            await safe_ws.send({
                "type": "files",
                "content": result
            })

        return result

    except Exception as e:
        await log_chat(f"Error getting files: {e}", safe_ws)

        if not safe_ws.is_closed:
            await safe_ws.send({
                "type": "error",
                "content": str(e),
                "code": "FILE_TREE_ERROR"
            })

        return {"error": str(e)}


def sanitize_tool_call(call):
    """
    Normalize tool call safely without losing args.
    """

    import json

    name = None
    args = {}

    # -------------------------------
    # Extract name
    # -------------------------------
    if isinstance(call, dict):
        name = call.get("name")

        # Try multiple keys
        raw_args = (
            call.get("args")
            or call.get("arguments")
            or call.get("input")
        )

    else:
        name = getattr(call, "name", None)
        raw_args = (
            getattr(call, "args", None)
            or getattr(call, "arguments", None)
        )

    # -------------------------------
    # Parse args SAFELY
    # -------------------------------
    if isinstance(raw_args, dict):
        args = raw_args  # ✅ already good

    elif isinstance(raw_args, str):
        try:
            args = json.loads(raw_args)
        except Exception:
            # ⚠️ KEEP RAW STRING (don't drop!)
            args = {"raw": raw_args}

    else:
        args = {}

    return {
        "name": name,
        "args": args
    }

def clean_up_response(response):
    """
    Extract final text and tool calls from agent/LLM response.

    Returns:
        {
            "text": str,
            "tool_calls": list
        }
    """

    def extract_text(content):
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            for item in reversed(content):
                if isinstance(item, dict):
                    if item.get("text"):
                        return item["text"]
                    if item.get("structured_response"):
                        return item["structured_response"]
            return None

        if isinstance(content, dict):
            return content.get("text") or content.get("structured_response")

        return None

    def extract_tool_calls(obj):
        calls = []

        # --- Attribute-based (AIMessage objects) ---
        if hasattr(obj, "tool_calls") and obj.tool_calls:
            for c in obj.tool_calls:
                calls.append(sanitize_tool_call(c))

        if hasattr(obj, "invalid_tool_calls") and obj.invalid_tool_calls:
            for c in obj.invalid_tool_calls:
                calls.append(sanitize_tool_call(c))

        # --- additional_kwargs (DeepSeek / OpenAI style) ---
        if hasattr(obj, "additional_kwargs") and isinstance(obj.additional_kwargs, dict):
            for c in obj.additional_kwargs.get("tool_calls", []):
                calls.append(sanitize_tool_call(c))

        # --- Dict-based ---
        if isinstance(obj, dict):
            for c in obj.get("tool_calls", []):
                calls.append(sanitize_tool_call(c))

            for c in obj.get("invalid_tool_calls", []):
                calls.append(sanitize_tool_call(c))

        return calls
    # -------------------------------
    # 1. structured_response
    # -------------------------------
    if isinstance(response, dict) and response.get("structured_response"):
        return {
            "text": response["structured_response"],
            "tool_calls": []
        }

    # -------------------------------
    # 2. messages (MAIN CASE)
    # -------------------------------
    if isinstance(response, dict) and isinstance(response.get("messages"), list):
        messages = response["messages"]

        for msg in reversed(messages):
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)

            text = extract_text(content)
            tool_calls = extract_tool_calls(msg)

            # priority: tool calls
            if tool_calls:
                return {
                    "text": text or "",
                    "tool_calls": tool_calls
                }

            # fallback: text
            if text:
                return {
                    "text": text,
                    "tool_calls": []
                }

    # -------------------------------
    # 3. direct dict
    # -------------------------------
    if isinstance(response, dict):
        text = extract_text(response.get("content"))
        tool_calls = extract_tool_calls(response)

        if text or tool_calls:
            return {
                "text": text or "",
                "tool_calls": tool_calls
            }

    # -------------------------------
    # 4. object (AIMessage)
    # -------------------------------
    if hasattr(response, "content"):
        text = extract_text(response.content)
        tool_calls = extract_tool_calls(response)

        if text or tool_calls:
            return {
                "text": text or "",
                "tool_calls": tool_calls
            }

    # -------------------------------
    # FINAL FALLBACK
    # -------------------------------
    return {
        "text": f"No readable response generated. {str(response).replace('`', '')}",
        "tool_calls": []
    }



async def generate_agent_response(session_id: str, user_message: str, safe_ws: SafeWebSocket):
    """
    Generate agent response with browser automation support.
    Now properly handles connection state.
    """
    global project_dir
    try:
        # Check if connection is still active
        if safe_ws.is_closed:
            print(f"Connection closed for {session_id}, skipping response generation")
            return
        
        
        # Build user message with any pending file contents
        file_context = ""
        if session_id in pending_file_contents and pending_file_contents[session_id]:
            parts = []
            for fc in pending_file_contents[session_id]:
                parts.append(f"--- File: {fc['filename']} ---\n{fc['content']}")
            file_context = "\n\n".join(parts)
            pending_file_contents[session_id] = []

        full_message = user_message
        if file_context:
            full_message = f"{user_message}\n\n--- ATTACHED FILES ---\n{file_context}"

        # Add user message
        user_message_obj = {"role": "user", "content": full_message}
        chat_manager.update_chat_history(user_message_obj, session_id)
        chat_history = chat_manager.get_chat_history(session_id)
        
        # Send thinking indicator
        await safe_ws.send({
            "type": "agent_thinking",
            "timestamp": datetime.now().isoformat(),
        })
        

        # Create wrapper functions that use the safe WebSocket
        async def request_input_wrapper(message: str, input_type: str = "text", options: list = None, fields: list = None) -> str:
            return await request_user_input(message, safe_ws, input_type=input_type, options=options, fields=fields)
        
        async def log_wrapper(message: str):
            await log_chat(message, safe_ws)
        

        async def file_tree_wrapper():
            return await file_tree_data(safe_ws)


        await file_tree_data(safe_ws)
        # Get agent response with timeout
        
        
        
        
        
        # -------------------------------
        # BROWSING FLOW
        # -------------------------------
        await log_wrapper("🌐 Browsing required. Running browser...")
        
        # Generate system prompt
        await log_wrapper("📝 Generating system prompt...")
        
        try:
            sys_prompt_gen = load_prompt("system_prompt_generator.md")
            # await log_chat(f"System prompt generator loaded: {sys_prompt_gen[:100] if sys_prompt_gen else 'None'}...", safe_ws)
        except FileNotFoundError:
            sys_prompt_gen = "Generate a system prompt for web browsing based on the conversation."
        
        # Check connection before browser launch
        if safe_ws.is_closed:
            await log_wrapper("Connection closed, aborting browser session")
            return
        
        # -------------------------------
        # BROWSER EXECUTION
        # -------------------------------
        async with async_playwright() as p:
            await log_wrapper("🚀 Launching browser...")
            launch_kwargs = {
                "headless": headless_mode,
                "args": [
                    "--disable-notifications",
                    "--disable-geolocation",
                    "--disable-infobars",
                    "--disable-gpu",
                    "--no-sandbox",
                ],
                "downloads_path": resolve_user_path("downloads"),
            }
            if GOOGLE_CHROME_PATH:
                launch_kwargs["executable_path"] = GOOGLE_CHROME_PATH
            browser = await p.chromium.launch(**launch_kwargs)
            
            context = await browser.new_context(permissions=[])
            # page = await context.new_page()
            
            # page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
            # context.on("page", lambda p: asyncio.create_task(p.close()))
            
            await log_wrapper("📄 Browser ready")
            session = BrowserSession(context)
            
            tools = build_tools(
                session=session,
                request_user_input=request_input_wrapper,
                log_chat=log_wrapper,
                file_tree_wrapper=file_tree_wrapper,
                base_path=project_dir,
                only_browser_tools=True
            )
            
            await log_chat(f"Project path: {project_dir}", safe_ws)
            sync_skills_to_project()
            agent = create_deep_agent(
                model=llm,
                tools=tools,
                backend = FilesystemBackend(root_dir=os.path.join(project_dir,"files"), virtual_mode=True),
                system_prompt=prompt,
                skills=["/skills/user/"],
            )
            await file_tree_data(safe_ws)
            await log_wrapper("🤖 Agent created. Running browser automation...")
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            try:
                response = await agent.ainvoke(
                    {
                        "messages": [
                            # {"role": "user", "content": user_message}
                        ] + chat_manager.get_chat_history(session_id)
                    },
                    config={"recursion_limit": 500, "configurable": {"thread_id": str(uuid.uuid4())}}
                )
            except Exception as e:
                await log_wrapper(f"⚠️ Agent error: {str(e)[:200]}")
                await log_wrapper("🔄 Retrying agent...")
                try:
                    response = await agent.ainvoke(
                        {
                            "messages": [
                                # {"role": "user", "content": user_message}
                            ] + chat_manager.get_chat_history(session_id) + 
                            [{"role": "system", "content": f"""
                                You are running again. Please continue from where you left last time. 
                                The last error was: {e}
                            """}]
                        },
                        config={"recursion_limit": 500}
                    )
                except Exception as e2:
                    await log_wrapper(f"❌ Agent retry failed: {str(e2)[:200]}")
                    response = f"Agent failed. Error: {e2}"
            
            await browser.close()
            await log_wrapper("🔒 Browser closed")
        
        # Process final response
        final_response = clean_up_response(response)
        print(response)
        await log_wrapper("✨ Final response generated")
        
        # Add final response to history
        chat_manager.update_chat_history({
            "role": "assistant", 
            "content": final_response['text'],
            "tool_calls": final_response['tool_calls']
        }, session_id)
        chat_history = chat_manager.get_chat_history(session_id)
        print(f"Final Response: {final_response['text']}")
        print(f"Tool Calls: {final_response['tool_calls']}")
        # Send final response
        if not safe_ws.is_closed:
            await safe_ws.send({
                "type": "message",
                "role": "assistant",
                "id": str(uuid.uuid4()),
                "content": final_response['text'],
                "timestamp": datetime.now().isoformat(),
            })
        await file_tree_data(safe_ws)
    except asyncio.CancelledError:
        print(f"Task cancelled for session {session_id}")
    except Exception as e:
        error_msg = f"Error generating response: {str(e)}"
        print(error_msg)
        try:
            if not safe_ws.is_closed:
                await safe_ws.send({
                    "type": "error",
                    "content": error_msg,
                    "timestamp": datetime.now().isoformat(),
                })
        except:
            pass

# -------------------------------
# WEB ENDPOINTS
# -------------------------------
@app.get("/")
async def root():
    return {"status": "AI Agent Server", "version": "3.0.0"}

@app.get("/health")
async def health():
    return {
        "status": "healthy", 
        "active_sessions": len(active_connections),
        "pending_inputs": len(pending_inputs)
    }



@app.websocket("/ws/{session_id}")
async def agent_session(websocket: WebSocket, session_id: str):
    await websocket.accept()
    global project_dir

    print(f"[+] Incoming connection: {session_id}")

    # 🔥 REUSE OR CREATE SESSION
    if session_id in safe_connections:
        safe_ws = safe_connections[session_id]
        await safe_ws.replace(websocket)
        print(f"[RECONNECTED] {session_id}")
    else:
        safe_ws = SafeWebSocket(websocket, session_id)
        safe_connections[session_id] = safe_ws
        print(f"[NEW SESSION] {session_id}")

    active_connections[session_id] = websocket
    connection_tasks.setdefault(session_id, set())

    # 🔥 DISCONNECT HANDLER
    async def on_disconnect(sid):
        print(f"[DISCONNECTED] {sid}")

    safe_ws.set_disconnect_handler(on_disconnect)

    try:
        await file_tree_data(safe_ws)

        chat_manager.get_chat_history(session_id)

        await safe_ws.send({
            "type": "system",
            "event": "connected",
            "session_id": session_id,
            "history_length": len(chat_manager.get_chat_history(session_id)),
            "timestamp": datetime.now().isoformat(),
        })

        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                data = json.loads(raw)

                msg_type = data.get("type", "message")
                print(f"[{session_id}] {msg_type}")
                # await log_chat(f"Received message: {data}", safe_ws)

                if msg_type == "message":
                    content = data.get("content", "").strip()
                    if not content:
                        continue

                    task = asyncio.create_task(
                        generate_agent_response(session_id, content, safe_ws)
                    )

                    connection_tasks[session_id].add(task)
                    task.add_done_callback(connection_tasks[session_id].discard)

                elif msg_type == "form_response":
                    request_id = data.get("request_id")
                    user_input = data.get("content", "")

                    if request_id in pending_inputs:
                        pending_inputs[request_id].set_result(user_input)

                elif msg_type == "clear_history":
                    chat_manager.clear_history(session_id)

                    await safe_ws.send({
                        "type": "system",
                        "event": "history_cleared",
                        "timestamp": datetime.now().isoformat(),
                    })

                elif msg_type == "file_upload":
                    import base64 as _b64
                    filename = data.get("filename", "").strip()
                    file_data = data.get("data", "")
                    if not filename or not file_data:
                        await safe_ws.send({
                            "type": "log",
                            "content": "File upload failed: missing filename or data",
                            "timestamp": datetime.now().isoformat(),
                        })
                        continue

                    # Sanitize filename
                    safe_name = os.path.basename(filename)
                    upload_dir = os.path.join(project_dir or "", "files", "uploads")
                    os.makedirs(upload_dir, exist_ok=True)
                    dest = os.path.join(upload_dir, safe_name)

                    # Prevent overwriting — append counter if exists
                    base, ext = os.path.splitext(dest)
                    counter = 1
                    while os.path.exists(dest):
                        dest = f"{base}_{counter}{ext}"
                        counter += 1

                    try:
                        raw_bytes = _b64.b64decode(file_data)
                        with open(dest, "wb") as f:
                            f.write(raw_bytes)

                        # Extract text content for agent context
                        content = extract_file_content(dest, os.path.basename(dest))
                        if session_id not in pending_file_contents:
                            pending_file_contents[session_id] = []
                        pending_file_contents[session_id].append({
                            "filename": os.path.basename(dest),
                            "content": content,
                        })

                        await log_chat(f"File uploaded: {os.path.basename(dest)} ({len(raw_bytes)} bytes)", safe_ws)
                        await file_tree_data(safe_ws)
                    except Exception as e:
                        await safe_ws.send({
                            "type": "log",
                            "content": f"File upload error: {e}",
                            "timestamp": datetime.now().isoformat(),
                        })

                elif msg_type == "ping":
                    await safe_ws.send({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat(),
                    })
                    if project_dir is not None:
                        await file_tree_data(safe_ws)
                        

                elif msg_type == "llmApiAuth":
                    api_key = data.get("api_key", "").strip()
                    model_tag = data.get("model_name", "deepseek-v4-flash").strip()
                    try:
                        global llm
                        global llm_deterministic
                        llm = await get_models(api_key, model_tag=model_tag)
                        llm_deterministic = await get_models(api_key, model_tag=model_tag, temperature=0.1)
                    except Exception as e:
                        print(f"[ERROR] {session_id}: {e}")
                        await safe_ws.send({
                            "type": "error",
                            "content": f"Error: {str(e)}",
                            "timestamp": datetime.now().isoformat(),
                        })
                    if llm is None:
                        await safe_ws.send({
                            "type": "llmApiAuthFailed",
                            "content": f"Check Api",
                            "timestamp": datetime.now().isoformat(),
                            "code": "WS_SEND_FAILED"
                        })
                        await safe_ws.close()
                        break

                elif msg_type=="folderPath":
                    
                    print(f"[FOLDER PATH] {project_dir}")
                    project_dir = data.get("folder_path", "").strip()
                    print(f"Data : {data}")

                elif msg_type == "headless":
                    global headless_mode
                    headless_mode = data.get("headless", False)
                    print(f"[HEADLESS] {headless_mode}")
            except asyncio.TimeoutError:
                continue

            except WebSocketDisconnect:
                print(f"[WS DISCONNECT] {session_id}")
                break

            except Exception as e:
                print(f"[ERROR] {session_id}: {e}")

    finally:
        await safe_ws.close()

        # 🔥 DELAYED CLEANUP (CRITICAL)
        async def delayed_cleanup():
            await asyncio.sleep(30)

            if safe_ws.is_closed:
                print(f"[CLEANUP] {session_id}")

                safe_connections.pop(session_id, None)
                active_connections.pop(session_id, None)
                connection_tasks.pop(session_id, None)

        asyncio.create_task(delayed_cleanup())
