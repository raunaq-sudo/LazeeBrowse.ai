import json
import os
import datetime
from typing import List, Dict, Optional
from langchain.tools import tool


def build_tools(browser_command, log_chat, base_path=None):
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
    async def get_search_results() -> list:
        """Extract search results from Google, DuckDuckGo, or Brave. Returns [{title, url, snippet}]."""
        await log_chat("Extracting search results")
        return await browser_command("get_search_results", {})

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
    # These tools are interrupted by HumanInTheLoopMiddleware via interrupt_on.
    # The tool functions are essentially stubs — the user's respond value
    # replaces the tool output entirely (the tool never executes).

    @tool
    async def get_user_confirmation(query: str) -> str:
        """Ask user a yes/no question. Returns the user's response."""
        return query

    @tool
    async def get_user_input_from_options(options: str) -> str:
        """Present numbered options to user. Format: '1. Red, 2. Green, 3. Blue'."""
        return options

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

    # ── UTILITY ──────────────────────────────────

    @tool
    async def get_current_date_time() -> str:
        """Get current date and time."""
        return datetime.datetime.now().strftime("%A, %d %B %Y %H:%M:%S")

    @tool
    async def get_total_tokens(pattern: str) -> str:
        """Get token count for files matching a regex pattern in the project directory. Use before reading any file to check size. Estimates ~4 chars per token."""
        import re as _re
        total_chars = 0
        file_count = 0
        matched_files = []
        try:
            files_dir = get_user_files_dir()
            if not os.path.isdir(files_dir):
                return "No files directory found."
            regex = _re.compile(pattern, _re.IGNORECASE)
            for root, dirs, files in os.walk(files_dir):
                for fname in files:
                    if fname.startswith("."):
                        continue
                    if not regex.search(fname):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        size = os.path.getsize(fpath)
                        total_chars += size
                        file_count += 1
                        rel = os.path.relpath(fpath, files_dir)
                        matched_files.append(f"{rel} ({size:,} chars)")
                    except Exception:
                        continue
            total_tokens = total_chars // 4
            if file_count == 0:
                return f"No files matching pattern '{pattern}'"
            listing = "\n".join(matched_files[:20])
            more = f"\n... and {file_count - 20} more" if file_count > 20 else ""
            return f"Matched: {file_count} files\n{listing}{more}\n\nEstimated tokens: ~{total_tokens:,}"
        except Exception as e:
            return f"Error: {e}"

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
        click, type_text, scroll, submit_form, press_key,
        get_page_text, get_all_links, get_search_results, get_all_headings, get_ui_schema, get_page_content,
        get_user_confirmation, get_user_input_from_options,
        write_file, read_file, delete_entry,
        get_current_date_time, get_total_tokens, action_logger,
    ]
