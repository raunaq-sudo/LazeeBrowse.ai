from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Dict, List, Set, Optional
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
from langchain_core.messages import AIMessage
from browser_tools_electron import build_tools, extract_text_from_file
from config import get_models, get_model_list
from prompts.deep_agent_browser import prompt
from tot_agent import create_tot_agent
import db

llm = None
llm_deterministic = None
project_dir = db.get_setting("project_dir") or None

app = FastAPI(title="LazeeBrowse.ai Server")

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

pending_browser_commands: Dict[str, asyncio.Future] = {}
active_connections: Dict[str, WebSocket] = {}
connection_tasks: Dict[str, Set[asyncio.Task]] = {}
session_modes: Dict[str, str] = {}  # session_id -> "browser_control" | "chat"
session_project_dirs: Dict[str, str] = {}  # session_id -> project_dir
user_input_futures: Dict[str, asyncio.Future] = {}  # session_id -> Future for interrupt resume

class ChatManager:
    """
    Owns chat history + activity log persistence for a single project directory.
    Instances are NOT session scoped — see `get_chat_manager()` below, which keys
    instances by project directory so every websocket session pointed at the same
    project shares one history store (and one sqlite file on disk).
    """
    def __init__(self):
        self.chat_histories: List[dict] = []
        self.activity_logs: List[dict] = []
        self.message_count = 0
        self.db_path: str | None = None
        self.memory_summary: str = ""
        self.MEMORY_WINDOW = 10

    def _get_db_path(self) -> str | None:
        return self.db_path

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
            CREATE TABLE IF NOT EXISTS conversation_memory (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        # Migrate legacy DBs (created without these columns) so they stay
        # readable and writable in place. ALTER ADD COLUMN only accepts
        # constant defaults, so add columns without one and backfill timestamps.
        for table in ("messages", "activity_log"):
            try:
                cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            except Exception:
                continue
            try:
                if "created_at" not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN created_at TEXT")
                    conn.execute(f"UPDATE {table} SET created_at = datetime('now') WHERE created_at IS NULL")
                    conn.commit()
            except Exception:
                pass
        try:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()]
            if "tool_calls" not in cols:
                conn.execute("ALTER TABLE messages ADD COLUMN tool_calls TEXT")
                conn.commit()
        except Exception:
            pass
        conn.close()

    def _resolve_db_path(self, project_dir: str) -> str:
        """Prefer an existing chat DB (either filename), else create chat_session.db."""
        plural = os.path.join(project_dir, "chat_sessions.db")
        singular = os.path.join(project_dir, "chat_session.db")
        if os.path.isfile(plural):
            return plural
        return singular

    def init_session(self, project_dir: str):
        """Load (or create) the sqlite DB for this project directory."""
        if not project_dir:
            return
        db_path = self._resolve_db_path(project_dir)
        self.db_path = db_path
        self._ensure_tables(db_path)
        self.chat_histories = self._load_history(db_path)
        self.activity_logs = self._load_activity_log(db_path)
        self.memory_summary = self._load_memory_summary(db_path)
        self.message_count = 0

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
            print(f"[DB LOAD] loaded {len(messages)} chat messages from {db_path}")
            for i, m in enumerate(messages):
                print(f"[DB LOAD]   [{i}] role={m['role']!r} content={m['content'][:80]!r}")
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

    def _load_memory_summary(self, db_path: str) -> str:
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT value FROM conversation_memory WHERE key = 'summary'"
            ).fetchone()
            conn.close()
            return row[0] if row and row[0] else ""
        except Exception:
            return ""

    def get_llm_messages(self) -> List[dict]:
        """Hybrid Rolling Memory: recent messages are kept intact (window) and
        older ones are condensed into a background summary prepended to the
        LLM input (which rides atop the system prompt)."""
        history = self.chat_histories[-self.MEMORY_WINDOW:]
        if not self.memory_summary:
            return list(history)
        return [
            {"role": "system", "content": f"Conversation summary (older context):\n{self.memory_summary}"},
        ] + list(history)

    def set_memory_summary(self, summary: str):
        self.memory_summary = (summary or "").strip()
        db_path = self._get_db_path()
        if not db_path or not self.memory_summary:
            return
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO conversation_memory (key, value, updated_at) VALUES ('summary', ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
                (self.memory_summary,),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MEMORY ERROR]: {e}")

    def prune_history_to_window(self, window: int = 0):
        """Drop the oldest messages beyond the rolling window, in memory and DB."""
        window = window or self.MEMORY_WINDOW
        self.chat_histories = self.chat_histories[-window:]
        db_path = self._get_db_path()
        if not db_path:
            return
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                "DELETE FROM messages WHERE id NOT IN "
                "(SELECT id FROM messages ORDER BY id DESC LIMIT ?)",
                (window,),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[PRUNE ERROR]: {e}")

    def _flush(self):
        db_path = self._get_db_path()
        if not db_path:
            return
        import sqlite3, json
        try:
            conn = sqlite3.connect(db_path)
            # Flush messages
            history = self.chat_histories
            existing = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            if len(history) > existing:
                for msg in history[existing:]:
                    conn.execute(
                        "INSERT INTO messages (role, content, tool_calls, created_at) VALUES (?, ?, ?, datetime('now'))",
                        (msg["role"], msg.get("content"), json.dumps(msg.get("tool_calls")) if msg.get("tool_calls") else None)
                    )
            # Flush activity logs
            logs = self.activity_logs
            existing_logs = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
            if len(logs) > existing_logs:
                for entry in logs[existing_logs:]:
                    conn.execute(
                        "INSERT INTO activity_log (type, content, name, input_text, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
                        (entry.get("type", "log"), entry.get("content"), entry.get("name"), entry.get("input_text"))
                    )
            conn.commit()
            conn.close()
            self.message_count = 0
        except Exception as e:
            print(f"[FLUSH ERROR]: {e}")

    def get_chat_history(self) -> List[dict]:
        return self.chat_histories

    def update_chat_history(self, message: dict):
        self.chat_histories.append(message)
        self.message_count += 1
        if self.message_count >= 20:
            self._flush()

    def add_activity_log(self, entry: dict):
        self.activity_logs.append(entry)

    def clear_history(self):
        self.chat_histories = []
        self.activity_logs = []
        self.memory_summary = ""
        db_path = self._get_db_path()
        if db_path:
            import sqlite3
            try:
                conn = sqlite3.connect(db_path)
                conn.execute("DELETE FROM messages")
                conn.execute("DELETE FROM activity_log")
                conn.execute("DELETE FROM conversation_memory")
                conn.commit()
                conn.close()
            except Exception:
                pass
        self.message_count = 0

    def flush(self):
        self._flush()


# ── CHAT MANAGER REGISTRY (project-dir scoped, NOT session scoped) ─────

chat_managers: Dict[str, ChatManager] = {}

def get_chat_manager(proj_dir: Optional[str]) -> Optional[ChatManager]:
    """
    Return the ChatManager for a project directory, loading its sqlite DB if it
    already exists on disk or creating a fresh one if it doesn't. Instances are
    cached by normalized project path so every session/connection pointed at the
    same project directory shares one in-memory history + one DB file, rather than
    each websocket session keeping its own isolated (and conflicting) history.
    """
    if not proj_dir:
        return None
    key = os.path.normpath(os.path.abspath(proj_dir))
    mgr = chat_managers.get(key)
    if mgr is None:
        mgr = ChatManager()
        mgr.init_session(proj_dir)
        chat_managers[key] = mgr
    return mgr

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

async def log_chat(message: str, safe_ws: SafeWebSocket, mgr: Optional[ChatManager] = None):
    timestamp = datetime.now().isoformat()
    await safe_ws.send({"type": "log", "content": message, "timestamp": timestamp})
    if mgr:
        mgr.add_activity_log({"type": "log", "content": message, "created_at": timestamp})

async def roll_conversation_memory(llm, mgr: Optional[ChatManager]):
    """Hybrid Rolling Memory compaction: fold everything older than the last
    N messages into a rolling summary, then prune the old messages from both
    memory and the DB (the summary itself is persisted too)."""
    if not llm or not mgr:
        return
    history = mgr.get_chat_history()
    window = mgr.MEMORY_WINDOW
    if len(history) <= window:
        return
    old = history[:-window]

    lines = []
    for m in old:
        role = m.get("role", "unknown")
        content = str(m.get("content") or "").strip()
        if content:
            lines.append(f"[{role}] {content[:1500]}")
    if not lines:
        return

    prompt = (
        "You maintain a running summary of a conversation between a user and an "
        "AI web-browsing agent that browses sites, runs JS, and produces reports.\n\n"
        f"Previous summary:\n{mgr.memory_summary or '(none)'}\n\n"
        f"New messages to fold in:\n{chr(10).join(lines)}\n\n"
        "Produce an updated summary (max ~200 words) that preserves: the user's "
        "goals and preferences, tasks requested, decisions made, key facts or data "
        "found, files/pages created, and any unresolved or ongoing work. "
        "Respond with the summary text only, no preamble."
    )
    try:
        from langchain_core.messages import HumanMessage
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        summary = str(response.content).strip()
    except Exception as e:
        print(f"[MEMORY SUMMARIZE ERROR]: {e}")
        return
    if not summary:
        return
    mgr.set_memory_summary(summary)
    mgr.prune_history_to_window(window)

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
    def __init__(self, safe_ws, mgr: Optional[ChatManager] = None):
        self.safe_ws = safe_ws
        self.mgr = mgr

    async def on_llm_new_token(self, token: str, **kwargs):
        if token.strip():
            await self.safe_ws.send({"type": "thinking_token", "content": token})

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs):
        name = serialized.get("name", "unknown")
        await self.safe_ws.send({"type": "tool_call", "name": name})
        if self.mgr:
            self.mgr.add_activity_log({
                "type": "tool_call", "name": name,
                "created_at": datetime.now().isoformat()
            })

    async def on_tool_end(self, output: str, **kwargs):
        pass

async def generate_agent_response(session_id: str, user_message: str, safe_ws: SafeWebSocket, attached_files: list = None, deep_dive: bool = False):
    try:
        if safe_ws.is_closed:
            return

        session_project_dir = session_project_dirs.get(session_id, project_dir)
        if not session_project_dir:
            await safe_ws.send({"type": "error", "content": "No project directory set. Please set a project folder before sending tasks.", "timestamp": datetime.now().isoformat()})
            return

        # Chat storage is keyed by project directory, not by session — this looks
        # up (or lazily creates) the shared ChatManager for this project.
        mgr = get_chat_manager(session_project_dir)
        if mgr is None:
            await safe_ws.send({"type": "error", "content": "Could not initialize chat history for this project directory.", "timestamp": datetime.now().isoformat()})
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
                        content = extract_text_from_file(full_path)
                        file_sections.append(f"--- FILE: {fname} ---\n{content}\n--- END FILE ---")
                    except Exception as e:
                        file_sections.append(f"--- FILE: {fname} ---\n[Error reading: {e}]\n--- END FILE ---")
            if file_sections:
                user_message = user_message + "\n\n--- ATTACHED FILES ---\n" + "\n".join(file_sections) + "\n--- END ATTACHED FILES ---"

        user_message_obj = {"role": "user", "content": user_message}
        mgr.update_chat_history(user_message_obj)

        await safe_ws.send({"type": "agent_thinking", "timestamp": datetime.now().isoformat()})

        async def log_wrapper(message: str):
            await log_chat(message, safe_ws, mgr)

        async def browser_command_wrapper(command: str, params: dict) -> any:
            return await send_browser_command(command, params, safe_ws)

        async def resolve_hitl(tool_name: str, tool_args: dict, description: str) -> dict:
            """Send a user_input_request to the frontend and return the user's decision."""
            if safe_ws.is_closed:
                return {"type": "reject", "message": "User disconnected"}
            await safe_ws.send({"type": "processing_request_completed"})
            await safe_ws.send({
                "type": "user_input_request",
                "tool": tool_name,
                "args": tool_args,
                "description": description,
            })
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
                return {"type": "respond", "message": decision_message}
            if decision_type == "edit":
                return {"type": "edit", "edited_action": {"name": tool_name, "args": user_data.get("edited_args", tool_args)}}
            if decision_type == "reject":
                return {"type": "reject", "message": decision_message}
            return {"type": "respond", "message": decision_message}

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

        if deep_dive:
            await log_wrapper("Deep Dive mode active — generating multiple strategies...")

            async def tot_event(typ: str, data: str):
                if safe_ws.is_closed:
                    return
                timestamp = datetime.now().isoformat()
                if typ == "tot_phase":
                    content = f"🔍 {data}"
                    await safe_ws.send({"type": "log", "content": content, "timestamp": timestamp})
                    mgr.add_activity_log({"type": "tot_phase", "content": data, "created_at": timestamp})
                elif typ == "tot_branches":
                    names = json.loads(data)
                    lines = "\n".join(f"  • {n}" for n in names)
                    content = f"Strategies identified:\n{lines}"
                    await safe_ws.send({"type": "log", "content": content, "timestamp": timestamp})
                    mgr.add_activity_log({"type": "tot_branches", "content": content, "created_at": timestamp})
                elif typ == "tot_scores":
                    scores = json.loads(data)
                    lines = "\n".join(f"  • {k}: {v}" for k, v in scores.items())
                    content = f"Strategy scores:\n{lines}"
                    await safe_ws.send({"type": "log", "content": content, "timestamp": timestamp})
                    mgr.add_activity_log({"type": "tot_scores", "content": content, "created_at": timestamp})
                elif typ == "tot_selected":
                    await safe_ws.send({"type": "log", "content": f"→ Selected: {data}", "timestamp": timestamp})
                    await safe_ws.send({"type": "thinking_token", "content": f"[Selected strategy: {data}]"})
                    mgr.add_activity_log({"type": "tot_selected", "content": data, "created_at": timestamp})
                elif typ == "tot_backtrack":
                    await safe_ws.send({"type": "log", "content": f"↩ Backtracking from: {data}", "timestamp": timestamp})
                    mgr.add_activity_log({"type": "tot_backtrack", "content": data, "created_at": timestamp})
                elif typ == "tot_progress":
                    await safe_ws.send({"type": "log", "content": data, "timestamp": timestamp})
                    mgr.add_activity_log({"type": "tot_progress", "content": data, "created_at": timestamp})
                elif typ == "tot_message":
                    mgr.update_chat_history({"role": "assistant", "content": data, "tool_calls": []})
                    print(f"[TOT DB] saving message: {data[:80]}")
                    if not safe_ws.is_closed:
                        await safe_ws.send({
                            "type": "tot_message",
                            "role": "assistant",
                            "id": str(uuid.uuid4()),
                            "content": data,
                            "timestamp": timestamp,
                        })
                elif typ == "tot_done":
                    await safe_ws.send({"type": "thinking_token", "content": "[ToT complete — synthesizing answer]"})
                    mgr.add_activity_log({"type": "tot_done", "content": "ToT complete — synthesizing answer", "created_at": timestamp})

                # Persist every ToT state update immediately (not just on the
                # 20-message batching threshold) so a mid-run crash/restart
                # doesn't lose the trace of what the agent tried.
                mgr.flush()

            tot_agent = create_tot_agent(llm, tools, session_project_dir=session_project_dir, on_event=tot_event, resolve_hitl=resolve_hitl)
            tot_state = {
                "messages": mgr.get_llm_messages(),
                "question": user_message,
                "branches": [],
                "selected_plan": "",
                "selected_steps": [],
                "current_idx": -1,
                "final_answer": "",
                "errors": [],
                "feedback_score": 0,
                "feedback_reasoning": "",
                "replan_count": 0,
            }
            result = await tot_agent.ainvoke(tot_state)
            final_text = result.get("final_answer", "No answer generated.")
            response = {"messages": [AIMessage(content=final_text)], "text": final_text, "tool_calls": []}

            mgr.update_chat_history({"role": "assistant", "content": final_text, "tool_calls": []})
            await roll_conversation_memory(llm, mgr)
            mgr.flush()
            if not safe_ws.is_closed:
                await safe_ws.send({
                    "type": "message",
                    "role": "assistant",
                    "id": str(uuid.uuid4()),
                    "content": final_text,
                    "timestamp": datetime.now().isoformat(),
                })
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

        callback_handler = StreamingCallbackHandler(safe_ws, mgr)
        config = {"recursion_limit": 1000, "configurable": {"thread_id": thread_id}, "callbacks": [callback_handler]}

        input_messages = {"messages": mgr.get_llm_messages()}
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

                # Ask the user for a decision (shared with ToT deep agents)
                decision = await resolve_hitl(tool_name, tool_args, action.get("description", ""))

                await safe_ws.send({"type": "agent_thinking", "timestamp": datetime.now().isoformat()})
                response = await agent.ainvoke(Command(resume={"decisions": [decision]}), config=config)

        except Exception as e:
            await log_wrapper(f"Agent error: {str(e)[:200]}")
            if response is None:
                response = {"messages": []}

        final_response = clean_up_response(response)

        mgr.update_chat_history({
            "role": "assistant",
            "content": final_response['text'],
            "tool_calls": final_response['tool_calls']
        })

        await roll_conversation_memory(llm, mgr)
        mgr.flush()

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
                    deep_dive = data.get("deep_dive", False)
                    task = asyncio.create_task(generate_agent_response(session_id, content, safe_ws, attached_files=attached, deep_dive=deep_dive))
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
                    sess_dir = session_project_dirs.get(session_id, project_dir)
                    mgr = get_chat_manager(sess_dir)
                    if mgr:
                        mgr.clear_history()
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
                    folder_path = data.get("folder_path", "").strip()
                    session_project_dirs[session_id] = folder_path
                    print(f"[PROJECT DIR] {session_id}: {folder_path}")

                    # Chat history is scoped to the project directory, not the
                    # session — this loads the existing sqlite DB for this
                    # project if one exists, or creates a new one if it doesn't.
                    mgr = get_chat_manager(folder_path)

                    if mgr:
                        # Replay stored chat messages so the frontend reloads
                        # the full conversation for this project.
                        for msg in mgr.get_chat_history():
                            await safe_ws.send({
                                "type": "message",
                                "role": msg.get("role", "assistant"),
                                "id": str(uuid.uuid4()),
                                "content": msg.get("content", ""),
                                "timestamp": datetime.now().isoformat(),
                            })

                        # Replay stored activity logs (tool calls, ToT progress, etc.)
                        for entry in mgr.activity_logs:
                            etype = entry.get("type", "log")
                            if etype == "tool_call":
                                await safe_ws.send({
                                    "type": "tool_call",
                                    "name": entry.get("name", "unknown"),
                                })
                            else:
                                await safe_ws.send({
                                    "type": "log",
                                    "content": entry.get("content", ""),
                                    "timestamp": entry.get("created_at", datetime.now().isoformat()),
                                })

                elif msg_type == "stop":
                    tasks = connection_tasks.get(session_id, set()).copy()
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await safe_ws.send({"type": "log", "content": "Execution stopped by user.", "timestamp": datetime.now().isoformat()})

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
        sess_dir = session_project_dirs.get(session_id)
        mgr = get_chat_manager(sess_dir) if sess_dir else None
        if mgr:
            mgr.flush()
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
    return {"status": "LazeeBrowse.ai Server", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "healthy", "active_sessions": len(active_connections)}