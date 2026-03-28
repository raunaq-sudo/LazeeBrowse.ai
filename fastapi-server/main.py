from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List
import json
from datetime import datetime
import uuid
import asyncio
import time

from playwright.async_api import async_playwright

from deepagents import create_deep_agent
from browser_tool import BrowserSession, build_tools
from langchain.agents import create_agent

from pydantic import BaseModel, Field
from typing import Optional

from config import llm

app = FastAPI(title="AI Agent WebSocket Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# -------------------------------
# HELPER FUNCTIONS
# -------------------------------
async def request_user_input(message: str, websocket: WebSocket) -> str:
    """
    Request input from user and wait for response.
    Returns the user's input as a string.
    """
    request_id = str(uuid.uuid4())
    
    # Create a future to wait for user response
    future = asyncio.Future()
    pending_inputs[request_id] = future
    
    try:
        # Send input request to client
        await websocket.send_text(json.dumps({
            "type": "form_input",
            "request_id": request_id,
            "role": "assistant",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        }))
        
        # Wait for user response (with 5 minute timeout)
        try:
            user_response = await asyncio.wait_for(future, timeout=300.0)
            return user_response
        except asyncio.TimeoutError:
            return "User did not respond in time"
    finally:
        # Clean up
        pending_inputs.pop(request_id, None)

async def log_chat(message: str, websocket: WebSocket):
    """Send log message to client"""
    await websocket.send_text(json.dumps({
        "type": "log",
        "content": message,
        "timestamp": datetime.now().isoformat(),
    }))

def clean_up_response(response) -> QueryRouterResponse:
    """Clean and parse agent response"""
    try:
        if hasattr(response, 'messages') and response.messages:
            # Handle agent response
            last_message = response.messages[-1]
            if hasattr(last_message, 'content'):
                content = last_message.content
                if isinstance(content, dict) and 'response' in content:
                    return QueryRouterResponse(**content)
                elif isinstance(content, str):
                    return QueryRouterResponse(browsing_required=False, response=content)
        elif isinstance(response, dict):
            return QueryRouterResponse(**response)
        elif isinstance(response, str):
            return QueryRouterResponse(browsing_required=False, response=response)
        elif hasattr(response, 'response'):
            return QueryRouterResponse(
                browsing_required=getattr(response, 'browsing_required', False),
                response=getattr(response, 'response', str(response))
            )
    except Exception as e:
        print(f"Error cleaning response: {e}")
    
    # Default fallback
    return QueryRouterResponse(browsing_required=False, response=str(response))

# -------------------------------
# AGENT RESPONSE GENERATION
# -------------------------------
async def generate_agent_response(session_id: str, user_message: str, websocket: WebSocket) -> str:
    """
    Generate agent response with browser automation support.
    Properly handles user input requests.
    """
    try:
        # Get chat history
        chat_history = chat_manager.get_chat_history(session_id)
        
        # Add user message
        user_message_obj = {"role": "user", "content": user_message}
        chat_manager.update_chat_history(user_message_obj, session_id)
        
        # Send thinking indicator
        await websocket.send_text(json.dumps({
            "type": "agent_thinking",
            "timestamp": datetime.now().isoformat(),
        }))
        
        # Load router prompt
        try:
            with open("conversational_agent_system_prompt.md", "r") as f:
                conversational_agent_prompt = f.read()
        except FileNotFoundError:
            conversational_agent_prompt = "You are a helpful assistant that can browse the web when needed. When you need information from the user, use the request_user_input tool."
        
        # Create wrapper functions that use the websocket
        async def request_input_wrapper(message: str) -> str:
            """Wrapper for request_user_input that returns the user's response"""
            return await request_user_input(message, websocket)
        
        async def log_wrapper(message: str):
            """Wrapper for log_chat"""
            await log_chat(message, websocket)
        
        # Create conversational agent with proper wrappers
        convo_agent = create_agent(
            model=llm,
            tools=build_tools(
                session=None, 
                request_user_input=request_input_wrapper,
                log_chat=log_wrapper, 
                misc_tools=True
            ),
            system_prompt=conversational_agent_prompt,
            response_format=QueryRouterResponse
        )
        
        # Get agent response
        response = await convo_agent.ainvoke({
            "messages": chat_history
        })
        
        parsed_response = clean_up_response(response)
        await log_wrapper(f"Conversational agent response: {parsed_response.response[:100] if parsed_response.response else 'None'}...")
        
        # Add assistant response to history
        chat_manager.update_chat_history({
            "role": "assistant", 
            "content": parsed_response.response
        }, session_id)
        
        # Send initial response
        await websocket.send_text(json.dumps({
            "type": "message",
            "role": "assistant",
            "id": str(uuid.uuid4()),
            "content": parsed_response.response,
            "timestamp": datetime.now().isoformat(),
        }))
        
        # Check if browsing is required
        if not parsed_response.browsing_required:
            return parsed_response.response
        
        # -------------------------------
        # BROWSING FLOW
        # -------------------------------
        await log_wrapper("🌐 Browsing required. Running browser...")
        
        # Generate system prompt
        await log_wrapper("📝 Generating system prompt...")
        
        try:
            with open("system_prompt_generator.md", "r") as f:
                sys_prompt_gen = f.read()
        except FileNotFoundError:
            sys_prompt_gen = "Generate a system prompt for web browsing based on the conversation."
        
        system_prompt_agent = create_agent(
            model=llm,
            system_prompt=sys_prompt_gen
        )
        
        response_sys_prompt = await system_prompt_agent.ainvoke({
            "messages": chat_manager.get_chat_history(session_id)
        })
        
        system_prompt = clean_up_response(response_sys_prompt).response
        await log_wrapper("✅ System prompt generated")
        
        # -------------------------------
        # BROWSER EXECUTION
        # -------------------------------
        async with async_playwright() as p:
            await log_wrapper("🚀 Launching browser...")
            browser = await p.chromium.launch(
                headless=False, 
                args=[
                    "--disable-notifications",
                    "--disable-geolocation",
                    "--disable-infobars",
                ], 
                downloads_path="files/downloads"
            )
            
            context = await browser.new_context(permissions=[])
            page = await context.new_page()
            
            # Disable JS dialogs
            page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
            
            # Block popup tabs
            context.on("page", lambda p: asyncio.create_task(p.close()))
            
            await log_wrapper("📄 Browser ready")
            session = BrowserSession(page)
            
            # Create tools with the wrapper functions
            tools = build_tools(
                session=session,
                request_user_input=request_input_wrapper,
                log_chat=log_wrapper
            )
            
            agent = create_deep_agent(
                model=llm,
                tools=tools,
                system_prompt=system_prompt,
            )
            
            await log_wrapper("🤖 Agent created. Running browser automation...")
            
            try:
                response = await agent.ainvoke(
                    {
                        "messages": [
                            {"role": "user", "content": user_message}
                        ] + chat_manager.get_chat_history(session_id)
                    },
                    config={"recursion_limit": 500}
                )
            except Exception as e:
                await log_wrapper(f"⚠️ Agent error: {str(e)[:200]}")
                await log_wrapper("🔄 Retrying agent...")
                try:
                    response = await agent.ainvoke(
                        {
                            "messages": [
                                {"role": "user", "content": user_message}
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
        await log_wrapper("✨ Final response generated")
        
        # Add final response to history
        chat_manager.update_chat_history({
            "role": "assistant", 
            "content": final_response.response
        }, session_id)
        
        # Send final response
        await websocket.send_text(json.dumps({
            "type": "message",
            "role": "assistant",
            "id": str(uuid.uuid4()),
            "content": final_response.response,
            "timestamp": datetime.now().isoformat(),
        }))
        
        return final_response.response
        
    except Exception as e:
        error_msg = f"Error generating response: {str(e)}"
        await log_chat(f"❌ {error_msg}", websocket)
        await websocket.send_text(json.dumps({
            "type": "error",
            "content": error_msg,
            "timestamp": datetime.now().isoformat(),
        }))
        return error_msg

# -------------------------------
# WEB ENDPOINTS
# -------------------------------
@app.get("/")
async def root():
    return {"status": "AI Agent Server", "version": "3.0.0"}

@app.get("/health")
async def health():
    return {"status": "healthy", "active_sessions": len(chat_manager.chat_histories)}

@app.websocket("/ws/{session_id}")
async def agent_session(websocket: WebSocket, session_id: str):
    await websocket.accept()
    
    print(f"[+] Session open: {session_id}")
    
    # Initialize chat history
    chat_manager.get_chat_history(session_id)
    
    await websocket.send_text(json.dumps({
        "type": "system",
        "event": "connected",
        "session_id": session_id,
        "history_length": len(chat_manager.get_chat_history(session_id)),
        "timestamp": datetime.now().isoformat(),
    }))
    
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "message")
            
            if msg_type == "message":
                content = data.get("content", "").strip()
                if not content:
                    continue
                
                # Generate agent response in background
                asyncio.create_task(generate_agent_response(session_id, content, websocket))
                
            elif msg_type == "form_response":
                # Handle user response to input request
                request_id = data.get("request_id")
                user_input = data.get("data", {}).get("value", "")
                
                # Resolve the pending future if it exists
                if request_id in pending_inputs:
                    pending_inputs[request_id].set_result(user_input)
                    await log_chat(f"📥 Received user input: {user_input[:50]}...", websocket)
                else:
                    await log_chat(f"⚠️ No pending request for ID: {request_id}", websocket)
                    
            elif msg_type == "clear_history":
                chat_manager.clear_history(session_id)
                await websocket.send_text(json.dumps({
                    "type": "system",
                    "event": "history_cleared",
                    "timestamp": datetime.now().isoformat(),
                }))
                print(f"[~] History cleared: {session_id}")
                
            elif msg_type == "ping":
                await websocket.send_text(json.dumps({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat(),
                }))
                
    except WebSocketDisconnect:
        print(f"[-] Session closed: {session_id}")
        # Clean up any pending futures for this session
        for request_id, future in list(pending_inputs.items()):
            if not future.done():
                future.set_exception(Exception("WebSocket disconnected"))
    except Exception as e:
        print(f"[!] Error ({session_id}): {e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "content": f"Server error: {str(e)}",
                "timestamp": datetime.now().isoformat(),
            }))
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")