import json
import os
import datetime
from typing import List, Dict, Optional
from langchain.tools import tool


def build_tools(browser_command, request_user_input, log_chat, base_path=None):
    """Create LangChain tools that control Electron's BrowserView via IPC."""

    def get_user_files_dir():
        base = os.path.join(base_path, "files") if base_path else "files"
        os.makedirs(base, exist_ok=True)
        return base

    def resolve_user_path(relative_path: str):
        base = get_user_files_dir()
        clean = os.path.normpath(relative_path).lstrip(os.sep)
        full_path = os.path.join(base, clean)
        if not os.path.abspath(full_path).startswith(os.path.abspath(base)):
            raise Exception("Invalid file path (security violation)")
        return full_path

    def refresh_file_tree():
        pass

    # ── BROWSER: NAVIGATION ──────────────────────

    @tool
    async def open_url(url: str) -> str:
        """Navigate the browser to a URL."""
        await log_chat(f"Navigating to {url}")
        result = await browser_command("navigate", {"url": url})
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        return f"Opened {url}"

    @tool
    async def get_url() -> str:
        """Get the current page URL."""
        return await browser_command("get_url", {})

    @tool
    async def get_title() -> str:
        """Get the current page title."""
        return await browser_command("get_title", {})

    @tool
    async def go_back() -> str:
        """Navigate back."""
        await browser_command("go_back", {})
        return "OK"

    @tool
    async def go_forward() -> str:
        """Navigate forward."""
        await browser_command("go_forward", {})
        return "OK"

    # ── BROWSER: INTERACTION ─────────────────────

    @tool
    async def click(selector: str) -> str:
        """Click an element by CSS selector."""
        await log_chat(f"Clicking {selector}")
        result = await browser_command("click", {"selector": selector})
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        return f"Clicked {selector}"

    @tool
    async def type_text(selector: str, text: str) -> str:
        """Type text into an input field."""
        await log_chat(f"Typing into {selector}")
        result = await browser_command("type", {"selector": selector, "text": text})
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        return f"Typed into {selector}"

    @tool
    async def scroll(amount: int = 500) -> str:
        """Scroll down (positive) or up (negative) by N pixels."""
        await browser_command("scroll", {"amount": amount})
        return f"Scrolled {amount}px"

    @tool
    async def submit_form() -> str:
        """Submit the current form."""
        await browser_command("submit_form", {})
        return "Form submitted"

    @tool
    async def press_key(key: str) -> str:
        """Press a keyboard key (Enter, Tab, Escape, ArrowDown, etc.)."""
        await browser_command("press_key", {"key": key})
        return f"Pressed {key}"

    @tool
    async def fill_any_form(form_elements: List[Dict[str, str]]) -> str:
        """Fill multiple form fields. Each element: {selector, value}. Prompts user if value missing."""
        await log_chat("Filling form")
        fields = [{"label": e.get("selector", ""), "placeholder": e.get("value", ""), "value": e.get("value", "")} for e in form_elements]

        user_response = await request_user_input("Fill in the form fields:", input_type="form", fields=fields)

        try:
            values = json.loads(user_response) if user_response.startswith("[") else [user_response]
        except:
            values = [user_response]

        results, errors = [], []
        for i, element in enumerate(form_elements):
            selector = element.get("selector")
            if not selector:
                errors.append("Missing selector")
                continue
            value = values[i] if i < len(values) else element.get("value", "")
            if value in ("null", "undefined") or (isinstance(value, str) and value.strip() == ""):
                value = element.get("value", "")
            try:
                result = await browser_command("type", {"selector": selector, "text": value})
                if isinstance(result, dict) and result.get("error"):
                    errors.append(f"{selector}: {result['error']}")
                else:
                    results.append(selector)
            except Exception as e:
                errors.append(f"{selector}: {e}")

        if results and not errors:
            await browser_command("submit_form", {})

        parts = []
        if results:
            parts.append(f"Filled: {', '.join(results)}")
        if errors:
            parts.append(f"Errors: {' | '.join(errors)}")
        return " | ".join(parts) if parts else "OK"

    # ── BROWSER: EXTRACTION ──────────────────────

    @tool
    async def get_page_text() -> str:
        """Get all visible text from the page."""
        await log_chat("Getting page text")
        return await browser_command("get_text", {})

    @tool
    async def get_all_links() -> list:
        """Get all links on the page with text and href."""
        await log_chat("Getting links")
        return await browser_command("get_links", {})

    @tool
    async def get_all_headings() -> list:
        """Get all headings (H1-H6) on the page."""
        await log_chat("Getting headings")
        return await browser_command("get_headings", {})

    @tool
    async def get_ui_schema(mode: str = "visible") -> list:
        """Extract interactive elements. Modes: visible (default), full."""
        await log_chat("Getting UI schema")
        return await browser_command("get_schema", {"mode": mode})

    @tool
    async def get_page_content() -> str:
        """Get the raw HTML of the page body."""
        return await browser_command("get_page_content", {})

    # ── USER INPUT ───────────────────────────────

    @tool
    async def get_user_confirmation(query: str) -> str:
        """Ask user a yes/no question. Returns 'true' or 'false'."""
        await log_chat("Asking user")
        try:
            user_response = await request_user_input(query, input_type="confirmation")
            if not user_response or user_response in ("null", "undefined"):
                return "User did not respond."
            return "true" if "yes" in user_response.lower() else "false" if "no" in user_response.lower() else user_response
        except Exception as e:
            return f"{e}"

    @tool
    async def get_user_input_from_options(options: str) -> str:
        """Present numbered options to user. Format: '1. Red, 2. Green, 3. Blue'."""
        await log_chat("Getting user choice")
        import re
        option_list = [opt.strip() for opt in re.split(r'\d+\.\s*', options) if opt.strip()]
        try:
            return await request_user_input("Select an option:", input_type="options", options=option_list)
        except Exception as e:
            return f"{e}"

    # ── FILE OPERATIONS ──────────────────────────

    @tool
    async def write_file(content: str, filename: str, append: bool = False) -> str:
        """Write content to a file. Set append=true to add to end."""
        mode = "a" if append else "w"
        await log_chat(f"Writing {filename}")
        try:
            full_path = resolve_user_path(filename)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, mode, encoding="utf-8") as f:
                f.write(content)
            return f"OK: {filename}"
        except Exception as e:
            return str(e)

    @tool
    async def read_file(filepath: str) -> str:
        """Read file contents."""
        await log_chat(f"Reading {filepath}")
        try:
            full_path = resolve_user_path(filepath)
            if not os.path.exists(full_path):
                return f"Not found: {filepath}"
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return str(e)

    @tool
    async def delete_entry(filepath: str) -> str:
        """Delete a file or directory."""
        import shutil
        await log_chat(f"Deleting {filepath}")
        try:
            full_path = resolve_user_path(filepath)
            if not os.path.exists(full_path):
                return f"Not found: {filepath}"
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)
            return f"OK: {filepath}"
        except Exception as e:
            return str(e)

    # ── MEMORY ───────────────────────────────────

    @tool
    async def update_memory(url: str, reason: str, observation: str) -> str:
        """Store an observation about a URL."""
        await log_chat(f"Updating memory: {url}")
        try:
            memory_path = os.path.join(get_user_files_dir(), "url_memory.json")
            memory = {}
            if os.path.exists(memory_path):
                try:
                    with open(memory_path, "r") as f:
                        memory = json.load(f)
                except json.JSONDecodeError:
                    memory = {}
            memory.setdefault(url, []).append({"reason": reason, "observation": observation})
            with open(memory_path, "w") as f:
                json.dump(memory, f)
            return "OK"
        except Exception as e:
            return str(e)

    @tool
    async def read_memory() -> str:
        """Read all stored URL observations."""
        try:
            memory_path = os.path.join(get_user_files_dir(), "url_memory.json")
            if not os.path.exists(memory_path):
                return "{}"
            with open(memory_path, "r") as f:
                return json.dumps(json.load(f), indent=2)
        except Exception as e:
            return str(e)

    # ── UTILITY ──────────────────────────────────

    @tool
    async def get_current_date_time() -> str:
        """Get current date and time."""
        return datetime.datetime.now().strftime("%A, %d %B %Y %H:%M:%S")

    @tool
    async def action_logger(action: str) -> str:
        """Log an action to the user."""
        try:
            await log_chat(action)
            return "OK"
        except:
            return "Error"

    # ── TOOL LIST ────────────────────────────────

    return [
        open_url, get_url, get_title, go_back, go_forward,
        click, type_text, scroll, submit_form, press_key, fill_any_form,
        get_page_text, get_all_links, get_all_headings, get_ui_schema, get_page_content,
        get_user_confirmation, get_user_input_from_options,
        write_file, read_file, delete_entry,
        update_memory, read_memory,
        get_current_date_time, action_logger,
    ]
