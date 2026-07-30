from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Dict, List, Set
import json
from datetime import datetime
import uuid
import asyncio
import os
import re

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from browser_tools_electron import build_tools
from config import get_models, get_model_list
from prompts.deep_agent_browser import prompt
import db

llm = None
llm_deterministic = None
project_dir = db.get_setting("project_dir") or None

app = FastAPI(title="AI Browser Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── SETTINGS ────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    return db.get_all_settings()

@app.post("/api/settings")
async def save_settings(request: Request):
    body = await request.json()
    api_keys = body.get("api_keys", {})
    if not api_keys and body.get("api_key"):
        api_keys = {body.get("provider", "deepseek"): body["api_key"]}
    db.save_all_settings(
        model_name=body.get("model_name"),
        project_dir=body.get("project_dir"),
        api_keys=api_keys or None,
    )
    return {"ok": True}

@app.get("/api/models")
async def list_models():
    return {"models": get_model_list()}

@app.get("/api/recent-projects")
async def list_recent_projects():
    return {"projects": db.get_recent_projects()}

@app.post("/api/recent-projects")
async def add_recent_project(request: Request):
    body = await request.json()
    path = body.get("path", "").strip()
    name = body.get("name", "")
    if not path:
        return JSONResponse({"error": "Missing path"}, status_code=400)
    if not name:
        name = path.split("/").pop() or path.split("\\").pop() or path
    db.upsert_recent_project(path, name)
    return {"ok": True}

@app.delete("/api/recent-projects")
async def remove_recent_project(request: Request):
    body = await request.json()
    path = body.get("path", "").strip()
    if not path:
        return JSONResponse({"error": "Missing path"}, status_code=400)
    # Safety check: only delete paths that look like project directories
    if not os.path.isdir(path) or len(path) < 5:
        return JSONResponse({"error": "Invalid path"}, status_code=400)
    import shutil
    shutil.rmtree(path, ignore_errors=True)
    db.delete_recent_project(path)
    return {"ok": True}

# ── STATE ───────────────────────────────────────

chat_manager = None
pending_browser_commands: Dict[str, asyncio.Future] = {}
active_connections: Dict[str, WebSocket] = {}
connection_tasks: Dict[str, Set[asyncio.Task]] = {}
session_modes: Dict[str, str] = {}  # session_id -> "browser_control" | "chat"
session_project_dirs: Dict[str, str] = {}  # session_id -> project_dir
user_input_futures: Dict[str, asyncio.Future] = {}  # session_id -> Future for interrupt resume

class ChatManager:
    def __init__(self):
        self.chat_histories: Dict[str, List[dict]] = {}
        self.activity_logs: Dict[str, List[dict]] = {}
        self.message_counters: Dict[str, int] = {}
        self.db_paths: Dict[str, str] = {}

    def _get_db_path(self, session_id: str) -> str | None:
        return self.db_paths.get(session_id)

    def _ensure_tables(self, db_path: str):
        import sqlite3
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT,
                tool_calls TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                content TEXT,
                name TEXT,
                input_text TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        conn.close()

    def init_session(self, session_id: str, project_dir: str):
        if not project_dir:
            return
        db_path = os.path.join(project_dir, "chat_session.db")
        self.db_paths[session_id] = db_path
        self._ensure_tables(db_path)
        self.chat_histories[session_id] = self._load_history(db_path)
        self.activity_logs[session_id] = self._load_activity_log(db_path)
        self.message_counters[session_id] = 0

    def _load_history(self, db_path: str) -> List[dict]:
        import sqlite3, json
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute("SELECT role, content, tool_calls, created_at FROM messages ORDER BY id").fetchall()
            conn.close()
            messages = []
            for role, content, tool_calls_str, created_at in rows:
                msg = {"role": role, "content": content or ""}
                if tool_calls_str:
                    try:
                        msg["tool_calls"] = json.loads(tool_calls_str)
                    except json.JSONDecodeError:
                        pass
                messages.append(msg)
            return messages
        except Exception:
            return []

    def _load_activity_log(self, db_path: str) -> List[dict]:
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute("SELECT type, content, name, input_text, created_at FROM activity_log ORDER BY id").fetchall()
            conn.close()
            return [
                {"type": typ, "content": content, "name": name, "input_text": input_text, "created_at": created_at}
                for typ, content, name, input_text, created_at in rows
            ]
        except Exception:
            return []

    def _flush(self, session_id: str):
        db_path = self._get_db_path(session_id)
        if not db_path:
            return
        import sqlite3, json
        try:
            conn = sqlite3.connect(db_path)
            # Flush messages
            history = self.chat_histories.get(session_id, [])
            existing = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            if len(history) > existing:
                for msg in history[existing:]:
                    conn.execute(
                        "INSERT INTO messages (role, content, tool_calls) VALUES (?, ?, ?)",
                        (msg["role"], msg.get("content"), json.dumps(msg.get("tool_calls")) if msg.get("tool_calls") else None)
                    )
            # Flush activity logs
            logs = self.activity_logs.get(session_id, [])
            existing_logs = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
            if len(logs) > existing_logs:
                for entry in logs[existing_logs:]:
                    conn.execute(
                        "INSERT INTO activity_log (type, content, name, input_text) VALUES (?, ?, ?, ?)",
                        (entry.get("type", "log"), entry.get("content"), entry.get("name"), entry.get("input_text"))
                    )
            conn.commit()
            conn.close()
            self.message_counters[session_id] = 0
        except Exception as e:
            print(f"[FLUSH ERROR] {session_id}: {e}")

    def get_chat_history(self, session_id: str) -> List[dict]:
        return self.chat_histories.setdefault(session_id, [])

    def update_chat_history(self, message: dict, session_id: str):
        self.chat_histories.setdefault(session_id, []).append(message)
        self.message_counters[session_id] = self.message_counters.get(session_id, 0) + 1
        if self.message_counters[session_id] >= 20:
            self._flush(session_id)

    def add_activity_log(self, session_id: str, entry: dict):
        self.activity_logs.setdefault(session_id, []).append(entry)

    def clear_history(self, session_id: str):
        self.chat_histories[session_id] = []
        self.activity_logs[session_id] = []
        db_path = self._get_db_path(session_id)
        if db_path:
            import sqlite3
            try:
                conn = sqlite3.connect(db_path)
                conn.execute("DELETE FROM messages")
                conn.execute("DELETE FROM activity_log")
                conn.commit()
                conn.close()
            except Exception:
                pass
        self.message_counters[session_id] = 0

    def flush(self, session_id: str):
        self._flush(session_id)

chat_manager = ChatManager()

# ── WEBSOCKET HELPERS ───────────────────────────

class SafeWebSocket:
    def __init__(self, websocket: WebSocket, session_id: str):
        self.websocket = websocket
        self.session_id = session_id
        self._closed = False
        self._lock = asyncio.Lock()

    async def send(self, data: dict) -> bool:
        if self._closed:
            return False
        async with self._lock:
            try:
                await asyncio.wait_for(self.websocket.send_text(json.dumps(data)), timeout=5)
                return True
            except Exception:
                self._closed = True
                return False

    async def close(self):
        if not self._closed:
            self._closed = True
            try:
                await self.websocket.close()
            except Exception:
                pass

    @property
    def is_closed(self):
        return self._closed

safe_connections: Dict[str, SafeWebSocket] = {}

# ── BROWSER COMMAND RELAY ───────────────────────

async def send_browser_command(command: str, params: dict, safe_ws: SafeWebSocket) -> any:
    """Send a command to Electron and wait for the result."""
    request_id = str(uuid.uuid4())
    future = asyncio.Future()
    pending_browser_commands[request_id] = future

    success = await safe_ws.send({
        "type": "browser_command",
        "command": command,
        "params": params,
        "request_id": request_id,
    })

    if not success:
        pending_browser_commands.pop(request_id, None)
        return {"error": "WebSocket connection closed"}

    try:
        result = await asyncio.wait_for(future, timeout=30.0)
        return result
    except asyncio.TimeoutError:
        pending_browser_commands.pop(request_id, None)
        return {"error": "Browser command timed out"}
    finally:
        pending_browser_commands.pop(request_id, None)

async def log_chat(message: str, safe_ws: SafeWebSocket):
    timestamp = datetime.now().isoformat()
    await safe_ws.send({"type": "log", "content": message, "timestamp": timestamp})
    chat_manager.add_activity_log(safe_ws.session_id, {"type": "log", "content": message, "created_at": timestamp})

# ── FILE HELPERS ────────────────────────────────

def get_user_files_dir():
    base = os.path.join(project_dir, "files")
    os.makedirs(base, exist_ok=True)
    return base

def resolve_user_path(relative_path: str):
    base = get_user_files_dir()
    clean = os.path.normpath(relative_path).lstrip(os.sep)
    full_path = os.path.join(base, clean)
    if not os.path.abspath(full_path).startswith(os.path.abspath(base)):
        raise Exception("Invalid file path (security violation)")
    return full_path

def get_resource_path(relative_path: str) -> str:
    import sys
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def load_prompt(filename: str) -> str:
    path = get_resource_path(f"prompts/{filename}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# ── RESPONSE CLEANUP ────────────────────────────

def clean_up_response(response):
    def extract_text(content):
        if isinstance(content, str): return content
        if isinstance(content, list):
            for item in reversed(content):
                if isinstance(item, dict):
                    if item.get("text"): return item["text"]
                    if item.get("structured_response"): return item["structured_response"]
            return None
        if isinstance(content, dict):
            return content.get("text") or content.get("structured_response")
        return None

    def extract_tool_calls(obj):
        calls = []
        try:
            tc = getattr(obj, "tool_calls", None) or []
            for c in tc: calls.append(sanitize_tool_call(c))
        except Exception: pass
        try:
            itc = getattr(obj, "invalid_tool_calls", None) or []
            for c in itc: calls.append(sanitize_tool_call(c))
        except Exception: pass
        try:
            ak = getattr(obj, "additional_kwargs", None)
            if isinstance(ak, dict):
                for c in ak.get("tool_calls", []): calls.append(sanitize_tool_call(c))
        except Exception: pass
        if isinstance(obj, dict):
            for c in obj.get("tool_calls", []): calls.append(sanitize_tool_call(c))
        return calls

    def sanitize_tool_call(call):
        if isinstance(call, dict):
            name = call.get("name")
            raw_args = call.get("args") or call.get("arguments")
        else:
            name = getattr(call, "name", None)
            raw_args = getattr(call, "args", None) or getattr(call, "arguments", None)
        if isinstance(raw_args, dict): args = raw_args
        elif isinstance(raw_args, str):
            try: args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError): args = {"raw": raw_args}
        else: args = {}
        return {"name": name, "args": args}

    def get_msg_type(msg):
        try: return getattr(msg, "type", None) or (msg.get("type") if isinstance(msg, dict) else None) or ""
        except Exception: return ""

    def get_msg_content(msg):
        try: return getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
        except Exception: return None

    def is_tool_result_noise(text):
        if not text: return True
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"): return True
        if stripped.startswith("[") and stripped.endswith("]"): return True
        if stripped.startswith('"') and stripped.endswith('"') and len(stripped) < 200: return True
        if stripped in ("OK", "ok", "Done", "done", "Error", "error", "None", "null"): return True
        json_ratio = sum(1 for c in stripped if c in '{}[]":') / max(len(stripped), 1)
        if json_ratio > 0.15 and len(stripped) > 100: return True
        if stripped.startswith('{"') and '"url"' in stripped[:200]: return True
        if stripped.startswith('[{"') and '"title"' in stripped[:200]: return True
        return False

    def is_tool_message(msg):
        return get_msg_type(msg) == "tool"

    def is_human_message(msg):
        return get_msg_type(msg) == "human"

    def clean_text(text):
        if not text: return text
        text = re.sub(r'```json\s*\n[\s\S]*?\n```', '', text)
        text = re.sub(r'```\s*\n[\s\S]*?\n```', '', text)
        text = re.sub(r'\{[^{}]{50,}\}', '', text)
        text = re.sub(r'\[[^\[\]]{50,}\]', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    if isinstance(response, dict) and isinstance(response.get("messages"), list):
        msgs = response["messages"]
        last_human_idx = -1
        for i in range(len(msgs) - 1, -1, -1):
            if is_human_message(msgs[i]):
                last_human_idx = i
                break
        new_msgs = msgs[last_human_idx + 1:] if last_human_idx >= 0 else msgs

        candidates = []
        for msg in reversed(new_msgs):
            if is_tool_message(msg): continue
            if is_human_message(msg): continue
            content = get_msg_content(msg)
            text = extract_text(content)
            if is_tool_result_noise(text): continue
            if text and len(text.strip()) > 20:
                cleaned = clean_text(text)
                if cleaned and len(cleaned) > 20 and not is_tool_result_noise(cleaned):
                    candidates.append({"text": cleaned, "tool_calls": []})
        if candidates:
            best = max(candidates, key=lambda c: len(c["text"]))
            return best
        for msg in reversed(new_msgs):
            if is_tool_message(msg): continue
            if is_human_message(msg): continue
            content = get_msg_content(msg)
            text = extract_text(content)
            if text and not is_tool_result_noise(text):
                return {"text": text, "tool_calls": []}

    if hasattr(response, "content"):
        text = extract_text(response.content)
        tool_calls = extract_tool_calls(response)
        if text or tool_calls: return {"text": text or "", "tool_calls": tool_calls}

    return {"text": str(response), "tool_calls": []}

# ── AGENT RESPONSE ──────────────────────────────

from langchain_core.callbacks import BaseCallbackHandler

class StreamingCallbackHandler(BaseCallbackHandler):
    def __init__(self, safe_ws):
        self.safe_ws = safe_ws

    async def on_llm_new_token(self, token: str, **kwargs):
        if token.strip():
            await self.safe_ws.send({"type": "thinking_token", "content": token})

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs):
        name = serialized.get("name", "unknown")
        await self.safe_ws.send({"type": "tool_call", "name": name, "input": input_str[:200]})
        chat_manager.add_activity_log(self.safe_ws.session_id, {
            "type": "tool_call", "name": name, "input_text": input_str[:200],
            "created_at": datetime.now().isoformat()
        })

    async def on_tool_end(self, output: str, **kwargs):
        pass

async def generate_agent_response(session_id: str, user_message: str, safe_ws: SafeWebSocket, attached_files: list = None):
    try:
        if safe_ws.is_closed:
            return

        session_project_dir = session_project_dirs.get(session_id, project_dir)
        if not session_project_dir:
            await safe_ws.send({"type": "error", "content": "No project directory set. Please set a project folder before sending tasks.", "timestamp": datetime.now().isoformat()})
            return

        if attached_files:
            file_sections = []
            for f in attached_files:
                fname = f.get("name", "unknown")
                fpath = f.get("path", "")
                if fpath:
                    full_path = os.path.normpath(os.path.join(session_project_dir, fpath))
                    if not full_path.startswith(os.path.normpath(session_project_dir)):
                        continue
                else:
                    full_path = None
                if full_path and os.path.isfile(full_path):
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                            content = fh.read()
                        file_sections.append(f"--- FILE: {fname} ---\n{content}\n--- END FILE ---")
                    except Exception as e:
                        file_sections.append(f"--- FILE: {fname} ---\n[Error reading: {e}]\n--- END FILE ---")
            if file_sections:
                user_message = user_message + "\n\n--- ATTACHED FILES ---\n" + "\n".join(file_sections) + "\n--- END ATTACHED FILES ---"

        user_message_obj = {"role": "user", "content": user_message}
        chat_manager.update_chat_history(user_message_obj, session_id)

        await safe_ws.send({"type": "agent_thinking", "timestamp": datetime.now().isoformat()})

        async def log_wrapper(message: str):
            await log_chat(message, safe_ws)

        async def browser_command_wrapper(command: str, params: dict) -> any:
            return await send_browser_command(command, params, safe_ws)

        async def file_tree_wrapper():
            pass  # No file tree in browser mode

        tools = build_tools(
            browser_command=browser_command_wrapper,
            log_chat=log_wrapper,
            base_path=session_project_dir,
        )

        if llm is None:
            await safe_ws.send({"type": "error", "content": "LLM not configured. Please check your API key and model settings.", "timestamp": datetime.now().isoformat()})
            return

        checkpointer = MemorySaver()
        thread_id = str(uuid.uuid4())

        agent = create_deep_agent(
            model=llm,
            tools=tools,
            backend=FilesystemBackend(root_dir=os.path.join(session_project_dir, "files"), virtual_mode=True),
            system_prompt=prompt,
            interrupt_on={
                "get_user_confirmation": True,
                "get_user_input_from_options": True,
            },
            checkpointer=checkpointer,
        )

        await log_wrapper("Agent running...")

        callback_handler = StreamingCallbackHandler(safe_ws)
        config = {"recursion_limit": 1000, "configurable": {"thread_id": thread_id}, "callbacks": [callback_handler]}

        input_messages = {"messages": chat_manager.get_chat_history(session_id)}
        response = None

        try:
            # Invoke agent — may interrupt for user input
            response = await agent.ainvoke(input_messages, config=config)

            # Handle potential interrupts
            while True:
                state_snapshot = await agent.aget_state(config)
                if not state_snapshot.next:
                    break  # Graph finished

                # Graph is interrupted — extract tool call info
                task = state_snapshot.tasks[0]
                hitl_request = task.interrupts[0].value if task.interrupts else None
                if not hitl_request:
                    break

                action_requests = hitl_request.get("action_requests", [])
                if not action_requests:
                    break

                action = action_requests[0]
                tool_name = action.get("name", "unknown")
                tool_args = action.get("args", {})

                # Send interrupt info to frontend
                await safe_ws.send({"type": "processing_request_completed"})
                await safe_ws.send({
                    "type": "user_input_request",
                    "tool": tool_name,
                    "args": tool_args,
                    "description": action.get("description", ""),
                })

                # Wait for user response
                user_future = asyncio.Future()
                user_input_futures[session_id] = user_future
                try:
                    user_data = await asyncio.wait_for(user_future, timeout=300.0)
                except asyncio.TimeoutError:
                    user_data = {"type": "reject", "message": "User did not respond in time"}
                finally:
                    user_input_futures.pop(session_id, None)

                decision_type = user_data.get("type", "respond")
                decision_message = user_data.get("content", "")

                if decision_type == "respond":
                    decisions = [{"type": "respond", "message": decision_message}]
                elif decision_type == "edit":
                    decisions = [{
                        "type": "edit",
                        "edited_action": {"name": tool_name, "args": user_data.get("edited_args", tool_args)},
                    }]
                else:
                    decisions = [{"type": decision_type, "message": decision_message}] if decision_type == "reject" else [{"type": "respond", "message": decision_message}]

                await safe_ws.send({"type": "agent_thinking", "timestamp": datetime.now().isoformat()})
                response = await agent.ainvoke(Command(resume={"decisions": decisions}), config=config)

        except Exception as e:
            await log_wrapper(f"Agent error: {str(e)[:200]}")
            if response is None:
                response = {"messages": []}

        final_response = clean_up_response(response)

        chat_manager.update_chat_history({
            "role": "assistant",
            "content": final_response['text'],
            "tool_calls": final_response['tool_calls']
        }, session_id)

        if not safe_ws.is_closed:
            await safe_ws.send({
                "type": "message",
                "role": "assistant",
                "id": str(uuid.uuid4()),
                "content": final_response['text'],
                "timestamp": datetime.now().isoformat(),
            })

    except asyncio.CancelledError:
        print(f"Task cancelled for session {session_id}")
    except Exception as e:
        print(f"Error: {e}")
        try:
            if not safe_ws.is_closed:
                await safe_ws.send({
                    "type": "error",
                    "content": str(e),
                    "timestamp": datetime.now().isoformat(),
                })
        except Exception:
            pass

# ── WEBSOCKET ENDPOINT ─────────────────────────

@app.websocket("/ws/{session_id}")
async def agent_session(websocket: WebSocket, session_id: str):
    await websocket.accept()
    global project_dir

    # Create a fresh SafeWebSocket for this connection
    safe_ws = SafeWebSocket(websocket, session_id)
    old_safe_ws = safe_connections.get(session_id)
    if old_safe_ws is not None:
        old_safe_ws._closed = True  # Mark old as closed so old tasks stop sending
    safe_connections[session_id] = safe_ws

    active_connections[session_id] = websocket
    connection_tasks.setdefault(session_id, set())

    try:
        await safe_ws.send({
            "type": "system",
            "event": "connected",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
        })

        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                data = json.loads(raw)
                msg_type = data.get("type", "")

                if msg_type == "message":
                    content = data.get("content", "").strip()
                    if not content:
                        continue
                    attached = data.get("attached_files", [])
                    task = asyncio.create_task(generate_agent_response(session_id, content, safe_ws, attached_files=attached))
                    connection_tasks[session_id].add(task)
                    task.add_done_callback(connection_tasks[session_id].discard)

                elif msg_type == "session_mode":
                    session_modes[session_id] = data.get("mode", "chat")
                    print(f"[SESSION MODE] {session_id}: {session_modes[session_id]}")

                elif msg_type == "browser_result":
                    request_id = data.get("request_id")
                    result = data.get("result")
                    if request_id in pending_browser_commands:
                        pending_browser_commands[request_id].set_result(result)

                elif msg_type == "user_input_response":
                    if session_id in user_input_futures:
                        user_input_futures[session_id].set_result(data)

                elif msg_type == "clear_history":
                    chat_manager.clear_history(session_id)
                    await safe_ws.send({"type": "system", "event": "history_cleared", "timestamp": datetime.now().isoformat()})

                elif msg_type == "llmApiAuth":
                    model_tag = data.get("model_name", "deepseek-v4-flash").strip()
                    provider = data.get("provider", "deepseek").strip()
                    api_key = data.get("api_key", "").strip()
                    if not api_key:
                        api_key = db.get_setting(f"api_key_{provider}") or ""
                    try:
                        global llm, llm_deterministic
                        llm = await get_models(api_key, model_tag=model_tag)
                        llm_deterministic = await get_models(api_key, model_tag=model_tag, temperature=0.1)
                    except Exception as e:
                        await safe_ws.send({"type": "error", "content": str(e), "timestamp": datetime.now().isoformat()})
                    if llm is None:
                        await safe_ws.send({"type": "llmApiAuthFailed", "content": "Check Api", "timestamp": datetime.now().isoformat()})
                        await safe_ws.close()
                        break

                elif msg_type == "folderPath":
                    session_project_dirs[session_id] = data.get("folder_path", "").strip()
                    print(f"[PROJECT DIR] {session_id}: {session_project_dirs[session_id]}")
                    project_dir_path = session_project_dirs[session_id]
                    chat_manager.init_session(session_id, project_dir_path)
                    # Send stored activity logs to frontend
                    stored_logs = chat_manager.activity_logs.get(session_id, [])
                    for entry in stored_logs:
                        etype = entry.get("type", "log")
                        if etype == "tool_call":
                            await safe_ws.send({
                                "type": "tool_call",
                                "name": entry.get("name", "unknown"),
                                "input": entry.get("input_text", ""),
                            })
                        else:
                            await safe_ws.send({
                                "type": "log",
                                "content": entry.get("content", ""),
                                "timestamp": entry.get("created_at", datetime.now().isoformat()),
                            })

                elif msg_type == "ping":
                    await safe_ws.send({"type": "pong", "timestamp": datetime.now().isoformat()})

            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                print(f"[WS DISCONNECT] {session_id}")
                break
            except Exception as e:
                print(f"[ERROR] {session_id}: {e}")

    finally:
        chat_manager.flush(session_id)
        await safe_ws.close()
        tasks = connection_tasks.pop(session_id, set())
        for task in tasks:
            if not task.done():
                task.cancel()
        async def delayed_cleanup():
            await asyncio.sleep(30)
            if safe_connections.get(session_id) is safe_ws:
                safe_connections.pop(session_id, None)
                active_connections.pop(session_id, None)
                connection_tasks.pop(session_id, None)
                session_modes.pop(session_id, None)
                session_project_dirs.pop(session_id, None)
                user_input_futures.pop(session_id, None)
        asyncio.create_task(delayed_cleanup())

@app.get("/")
async def root():
    return {"status": "AI Browser Server", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "healthy", "active_sessions": len(active_connections)}
