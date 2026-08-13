import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "settings.db")

PROVIDERS = ["deepseek", "google", "anthropic", "openai", "openrouter"]


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    return conn


def get_setting(key: str) -> str | None:
    conn = _connect()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else None


def set_setting(key: str, value: str):
    conn = _connect()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_api_keys() -> dict:
    keys = {}
    for p in PROVIDERS:
        keys[p] = get_setting(f"api_key_{p}") or ""
    return keys


def set_api_key(provider: str, key: str):
    if provider in PROVIDERS:
        set_setting(f"api_key_{provider}", key)


def get_all_settings() -> dict:
    return {
        "api_keys": get_api_keys(),
        "model_name": get_setting("model_name") or "",
        "project_dir": get_setting("project_dir") or "",
        "telegram_mode": get_setting("telegram_mode") or "",
        "telegram_bot_token": get_setting("telegram_bot_token") or "",
    }


def save_all_settings(model_name: str = None, project_dir: str = None, api_keys: dict = None, telegram_mode: str = None, telegram_bot_token: str = None):
    if model_name is not None:
        set_setting("model_name", model_name)
    if project_dir is not None:
        set_setting("project_dir", project_dir)
    if telegram_mode is not None:
        set_setting("telegram_mode", "on" if telegram_mode else "")
    if telegram_bot_token is not None:
        set_setting("telegram_bot_token", telegram_bot_token)
    if api_keys:
        for provider, key in api_keys.items():
            if provider in PROVIDERS and key:
                set_api_key(provider, key)


# ── RECENT PROJECTS ────────────────────────────

def _ensure_recent_projects_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS recent_projects (path TEXT PRIMARY KEY, name TEXT NOT NULL, last_opened TEXT NOT NULL)")


def get_recent_projects() -> list[dict]:
    conn = _connect()
    _ensure_recent_projects_table(conn)
    rows = conn.execute("SELECT path, name, last_opened FROM recent_projects ORDER BY last_opened DESC LIMIT 20").fetchall()
    conn.close()
    return [{"path": r[0], "name": r[1], "lastOpened": r[2]} for r in rows]


def upsert_recent_project(path: str, name: str):
    conn = _connect()
    _ensure_recent_projects_table(conn)
    conn.execute("DELETE FROM recent_projects WHERE path = ?", (path,))
    conn.execute("INSERT INTO recent_projects (path, name, last_opened) VALUES (?, ?, datetime('now'))", (path, name))
    # Keep only 20
    conn.execute("DELETE FROM recent_projects WHERE path NOT IN (SELECT path FROM recent_projects ORDER BY last_opened DESC LIMIT 20)")
    conn.commit()
    conn.close()


def delete_recent_project(path: str):
    conn = _connect()
    _ensure_recent_projects_table(conn)
    conn.execute("DELETE FROM recent_projects WHERE path = ?", (path,))
    conn.commit()
    conn.close()
