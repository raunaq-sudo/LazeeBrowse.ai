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
        "skills_dir": get_setting("skills_dir") or "",
    }


def save_all_settings(model_name: str = None, project_dir: str = None, api_keys: dict = None, skills_dir: str = None):
    if model_name is not None:
        set_setting("model_name", model_name)
    if project_dir is not None:
        set_setting("project_dir", project_dir)
    if skills_dir is not None:
        set_setting("skills_dir", skills_dir)
    if api_keys:
        for provider, key in api_keys.items():
            if provider in PROVIDERS and key:
                set_api_key(provider, key)
