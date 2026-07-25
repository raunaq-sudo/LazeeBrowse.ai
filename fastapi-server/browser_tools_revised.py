import asyncio
from dotenv import load_dotenv
load_dotenv()
import os
import shutil
from typing import List, Dict, Optional
import json
import datetime
from bs4 import BeautifulSoup
import re
from langchain.tools import tool


def build_tools(session, request_user_input, log_chat, misc_tools=False, only_browser_tools=False, file_tree_wrapper=None, base_path=None):
    """Create LangChain tools bound to a BrowserSession instance."""

    # ── HELPERS ──────────────────────────────────

    def get_user_files_dir():
        base = os.path.join(base_path, "files")
        os.makedirs(base, exist_ok=True)
        return base

    def resolve_user_path(relative_path: str):
        base = get_user_files_dir()
        clean = os.path.normpath(relative_path).lstrip(os.sep)
        full_path = os.path.join(base, clean)
        if not os.path.abspath(full_path).startswith(os.path.abspath(base)):
            raise Exception("Invalid file path (security violation)")
        return full_path

    def get_user_memory_path():
        base = get_user_files_dir()
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, "url_memory.json")
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write("{}")
        return path

    def refresh_file_tree():
        if file_tree_wrapper:
            return file_tree_wrapper()

    # ── BROWSER: NAVIGATION ──────────────────────

    @tool
    async def open_url(url: str, page_name: Optional[str] = None) -> str:
        """Navigate browser to a URL. Returns visible UI schema."""
        await log_chat(f"Opening {url}")
        try:
            await session.open_url(url, page_name)
            return await session.get_ui_schema(page_name, 'visible')
        except Exception as e:
            await log_chat(f"Error opening {url}: {e}")
            return f"{e}"

    @tool
    async def open_new_tab(url, page_name) -> str:
        """Open a new browser tab with the given URL and name."""
        await log_chat("Opening new tab")
        try:
            return await session.new_page(page_name, url=url)
        except Exception as e:
            return f"{e}"

    @tool
    async def list_tabs(detailed: bool = False) -> str:
        """List open browser tabs. Set detailed=true for URLs and titles."""
        await log_chat("Listing tabs")
        try:
            return await session.list_tabs_detailed() if detailed else await session.list_tabs()
        except Exception as e:
            return f"{e}"

    @tool
    async def close_tab(name: str) -> str:
        """Close a browser tab by name."""
        await log_chat(f"Closing tab {name}")
        try:
            return await session.close_tab(name)
        except Exception as e:
            return f"{e}"

    @tool
    async def switch_tab(name: str) -> str:
        """Switch to a browser tab by name."""
        await log_chat(f"Switching to tab {name}")
        try:
            return await session.switch_tab(name)
        except Exception as e:
            return f"{e}"

    @tool
    async def find_tab_by_url(keyword: str) -> str:
        """Find a tab whose URL contains the given keyword."""
        await log_chat(f"Searching for tab: {keyword}")
        try:
            return await session.find_tab_by_url(keyword)
        except Exception as e:
            return str(e)

    # ── BROWSER: INTERACTION ─────────────────────

    @tool
    async def click(selector: str, page_name: Optional[str] = None) -> str:
        """Click an element. Selector can be CSS, text=..., or button:has-text(...)."""
        await log_chat(f"Clicking {selector}")
        try:
            return await session.click(selector, page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def type_text(selector: str, text: str, page_name: Optional[str] = None) -> str:
        """Type text into an input field."""
        await log_chat(f"Typing into {selector}")
        try:
            return await session.type_text(selector, text, page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def scroll(amount: int, page_name: Optional[str] = None) -> str:
        """Scroll down by N pixels."""
        await log_chat(f"Scrolling {amount}px")
        try:
            return await session.scroll(amount, page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def submit_form(page_name) -> str:
        """Submit the current form on the page."""
        await log_chat("Submitting form")
        try:
            return await session.submit_form(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def fill_any_form(form_elements: List[Dict[str, str]], page_name) -> str:
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
                await session.clear(selector, page_name)
            except:
                pass
            try:
                await session.type_text(selector, value, page_name)
                results.append(selector)
            except Exception as e:
                errors.append(f"{selector}: {e}")

        if results and not errors:
            await session.submit_form(page_name)

        parts = []
        if results:
            parts.append(f"Filled: {', '.join(results)}")
        if errors:
            parts.append(f"Errors: {' | '.join(errors)}")
        return " | ".join(parts) if parts else "OK"

    @tool
    async def upload_file(selector: str, file_path: str, use_click: bool = False) -> str:
        """Upload a file to an input field. Set use_click=true to click a button first."""
        await log_chat(f"Uploading {file_path}")
        try:
            if use_click:
                return await session.upload_with_click(selector, file_path)
            return await session.upload_file(selector, file_path)
        except Exception as e:
            return f"{e}"

    # ── BROWSER: EXTRACTION ──────────────────────

    @tool
    async def get_page_text(page_name: Optional[str] = None) -> str:
        """Get all visible text from the page."""
        await log_chat("Getting page text")
        try:
            return await session.get_page_text(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_title(page_name: Optional[str] = None) -> str:
        """Get the page title."""
        await log_chat("Getting page title")
        try:
            return await session.get_title(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_ui_schema(page_name: Optional[str] = None, mode: str = None) -> list:
        """Extract UI schema. Modes: visible (default), interactive, full."""
        await log_chat("Getting UI schema")
        try:
            return await session.get_ui_schema(page_name, mode)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_visible_modal_schema(page_name: Optional[str] = None) -> list:
        """Get elements from any visible modal/overlay."""
        await log_chat("Getting modal schema")
        try:
            return await session.get_visible_modal_schema(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_all_links(page_name: Optional[str] = None, with_text: bool = False) -> list:
        """Extract all hyperlinks. Set with_text=true for text+URL pairs."""
        await log_chat("Getting links")
        try:
            return await session.get_all_links_with_text(page_name) if with_text else await session.get_all_links(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_all_headings(page_name: Optional[str] = None) -> list:
        """Extract all H1-H6 headings."""
        await log_chat("Getting headings")
        try:
            return await session.get_all_headings(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def search_url(page_name: str, query: str) -> str:
        """Search using a search bar on the page."""
        await log_chat(f"Searching: {query}")
        try:
            return await session.search_url(page_name, query)
        except Exception as e:
            return f"{e}"

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
        option_list = [opt.strip() for opt in re.split(r'\d+\.\s*', options) if opt.strip()]
        try:
            return await request_user_input("Select an option:", input_type="options", options=option_list)
        except Exception as e:
            return f"{e}"

    # ── FILE OPERATIONS ──────────────────────────

    @tool
    async def get_all_files():
        """List all files in the project directory."""
        await log_chat("Getting file tree")
        try:
            if file_tree_wrapper:
                return await file_tree_wrapper()
            base_dir = get_user_files_dir()
            nodes = []
            for root, dirs, files in os.walk(base_dir):
                for d in dirs:
                    fp = os.path.join(root, d)
                    rel = os.path.relpath(fp, base_dir)
                    nodes.append({"name": d, "path": fp, "project_path": f"files/{rel.replace(os.sep, '/')}", "type": "folder"})
                for f in files:
                    fp = os.path.join(root, f)
                    rel = os.path.relpath(fp, base_dir)
                    nodes.append({"name": f, "path": fp, "project_path": f"files/{rel.replace(os.sep, '/')}", "type": "file"})
            return {"nodes": nodes}
        except Exception as e:
            return {"error": str(e)}

    @tool
    async def write_file(content: str, filename: str, append: bool = False) -> str:
        """Write content to a file. Set append=true to add to end instead of overwrite."""
        mode = "a" if append else "w"
        action = "Appending" if append else "Saving"
        await log_chat(f"{action} {filename}")
        try:
            full_path = resolve_user_path(filename)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, mode, encoding="utf-8") as f:
                f.write(content)
            await refresh_file_tree()
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
        await log_chat(f"Deleting {filepath}")
        try:
            full_path = resolve_user_path(filepath)
            if not os.path.exists(full_path):
                return f"Not found: {filepath}"
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)
            await refresh_file_tree()
            return f"OK: {filepath}"
        except Exception as e:
            return str(e)

    @tool
    async def create_directory(dirname: str) -> str:
        """Create a directory."""
        await log_chat(f"Creating dir {dirname}")
        try:
            dir_path = resolve_user_path(dirname)
            if os.path.exists(dir_path):
                return "Already exists"
            os.makedirs(dir_path, exist_ok=True)
            await refresh_file_tree()
            return f"OK: {dirname}"
        except Exception as e:
            return str(e)

    @tool
    async def move_entry(src: str, dst: str) -> str:
        """Move or rename a file/directory."""
        await log_chat(f"Moving {src} → {dst}")
        try:
            src_path = resolve_user_path(src)
            dst_path = resolve_user_path(dst)
            if not os.path.exists(src_path):
                return "Source not found"
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.move(src_path, dst_path)
            await refresh_file_tree()
            return f"OK: {src} → {dst}"
        except Exception as e:
            return str(e)

    @tool
    async def convert_md(filepath: str, output_type: str, output_filename: str) -> str:
        """Convert Markdown to PDF or DOCX."""
        await log_chat(f"Converting {filepath} → {output_type}")
        try:
            import pypandoc
            if output_type not in ("pdf", "docx"):
                return "Invalid type. Use pdf or docx."
            if not os.path.exists(filepath):
                return f"Not found: {filepath}"
            os.makedirs("files", exist_ok=True)
            output_path = os.path.join("files", output_filename)
            try:
                pypandoc.get_pandoc_version()
            except:
                pypandoc.download_pandoc()
            extra_args = ["--standalone"]
            if output_type == "pdf":
                extra_args.append("--pdf-engine=xelatex")
            pypandoc.convert_file(filepath, output_type, outputfile=output_path, extra_args=extra_args)
            return f"OK: {output_path}"
        except Exception as e:
            return f"Failed: {e}"

    # ── MEMORY ───────────────────────────────────

    @tool
    async def update_memory(url: str, reason: str, observation: str) -> str:
        """Store an observation about a URL."""
        await log_chat(f"Updating memory: {url}")
        try:
            file_path = get_user_memory_path()
            memory = {}
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r") as f:
                        memory = json.load(f)
                except json.JSONDecodeError:
                    memory = {}
            memory.setdefault(url, []).append({"reason": reason, "observation": observation})
            tmp_path = file_path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(memory, f)
            os.replace(tmp_path, file_path)
            return "OK"
        except Exception as e:
            return str(e)

    @tool
    async def read_memory() -> str:
        """Read all stored URL observations."""
        await log_chat("Reading memory")
        try:
            file_path = get_user_memory_path()
            if not os.path.exists(file_path):
                return "{}"
            with open(file_path, "r") as f:
                return json.dumps(json.load(f), indent=2)
        except Exception as e:
            return str(e)

    @tool
    async def clear_memory() -> str:
        """Clear all URL observations."""
        await log_chat("Clearing memory")
        try:
            file_path = get_user_memory_path()
            if os.path.exists(file_path):
                os.remove(file_path)
            return "OK"
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

    # ── TOOL LISTS ───────────────────────────────

    browser_tools = [
        open_url, open_new_tab, click, type_text, scroll,
        get_page_text, get_title, get_ui_schema, get_visible_modal_schema,
        get_all_links, get_all_headings, submit_form, fill_any_form,
        upload_file, list_tabs, close_tab, switch_tab, search_url, find_tab_by_url,
    ]

    misc_tools_list = [
        get_user_confirmation, get_user_input_from_options,
        get_all_files, write_file, read_file, delete_entry,
        create_directory, move_entry, convert_md,
        update_memory, read_memory, clear_memory,
        get_current_date_time, action_logger,
    ]

    if misc_tools:
        return misc_tools_list
    elif only_browser_tools:
        return browser_tools + misc_tools_list
    else:
        return browser_tools + misc_tools_list
