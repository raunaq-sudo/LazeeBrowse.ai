import asyncio
from dotenv import load_dotenv
load_dotenv()
import os
import time
import shutil
from typing import List, Dict

import pypandoc
import sys
import json
import datetime

def get_base_path():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.getcwd()

def get_user_memory_path(base_path: str):
    base = base_path
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "url_memory.json")

def get_user_files_dir(base_path: str):
    base = os.path.join(base_path, "files")
    os.makedirs(base, exist_ok=True)
    return base

def resolve_user_path(base_path, relative_path: str):
    base = get_user_files_dir(base_path)
    return os.path.join(base, relative_path.replace("files/", ""))


import os
from typing import Dict, Optional


class BrowserSession:
    def __init__(self, context):
        self.context = context
        self.pages: Dict[str, any] = {}
        self.max_timeout = 5000
        self.active_page: Optional[str] = None

        # Auto-detect new tabs
        self.context.on("page", self._on_new_page)

    # ---------------- TAB MANAGEMENT ---------------- #

    async def _on_new_page(self, page):
        await page.wait_for_load_state()
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
        name = f"auto_{len(self.pages)+1}"
        self.pages[name] = page
        self.active_page = name
        print(f"[NEW TAB] {name} -> {page.url}")

    async def new_page(self, name: str, url: str):
        # Prevent duplicate tabs
        for existing_name, p in self.pages.items():
            if url in p.url:
                return f"[INFO] Reusing tab '{existing_name}'"

        page = await self.context.new_page()
        await page.goto(url, timeout=self.max_timeout)
        await page.wait_for_load_state("networkidle")

        self.pages[name] = page
        self.active_page = name

        return f"[OPENED] {url} -> {name}"

    async def get_page(self, name: Optional[str] = None):
        name = name or self.active_page
        if name not in self.pages:
            # Create new page
            print("New page opened. As Name of page was not found.")
            await self.new_page(name=name, url="https://www.duckduckgo.com")
        
        if name is None and self.active_page is None:
            raise Exception("No active page and no page name provided")
        
        if name is None and self.active_page is not None:
            name = self.active_page
            

        return self.pages[name]

    def list_tabs(self):
        return list(self.pages.keys())

    async def list_tabs_detailed(self):
        result = []
        for name, page in self.pages.items():
            try:
                result.append({
                    "name": name,
                    "url": page.url,
                    "title": await page.title()
                })
            except:
                result.append({
                    "name": name,
                    "url": page.url,
                    "title": "Unavailable"
                })
        return result

    async def close_page(self, name: str):
        page = await self.get_page(name)
        await page.close()
        del self.pages[name]

        if self.active_page == name:
            self.active_page = next(iter(self.pages), None)

        return f"[CLOSED] {name}"

    def switch_tab(self, name: str):
        if name not in self.pages:
            raise Exception(f"Tab '{name}' not found")
        self.active_page = name
        return f"[SWITCHED] {name}"

    def find_tab_by_url(self, keyword: str):
        for name, page in self.pages.items():
            if keyword in page.url:
                return name
        return None

    # ---------------- ACTIONS ---------------- #

    async def open_url(self, url: str, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        await page.goto(url, timeout=self.max_timeout)
        await page.wait_for_load_state("networkidle")
        return f"[{page_name or self.active_page}] Opened {url}"

    async def click(self, selector: str, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        await page.click(selector, timeout=self.max_timeout)
        return f"[CLICK] {selector}"

    async def type_text(self, selector: str, text: str, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        await page.fill(selector, "")
        await page.type(selector, text)
        return f"[TYPE] {text}"

    async def scroll(self, amount: int = 1000, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        await page.mouse.wheel(0, amount)
        return f"[SCROLL] {amount}px"

    async def clear(self, selector: str, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        await page.fill(selector, "")
        return f"[CLEAR] {selector}"

    async def submit_form(self, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        await page.keyboard.press("Enter")
        return "[FORM SUBMITTED]"

    # ---------------- EXTRACTION ---------------- #

    async def get_page_text(self, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        return await page.inner_text("body")

    async def get_title(self, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        return await page.title()

    async def get_all_links(self, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        return await page.evaluate("""
        () => Array.from(document.querySelectorAll("a")).map(a => a.href)
        """)

    async def get_all_links_with_text(self, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        return await page.evaluate("""
        () => Array.from(document.querySelectorAll("a"))
            .map(a => ({ text: a.innerText, href: a.href }))
        """)

    async def get_all_headings(self, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        return await page.evaluate("""
        () => Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6"))
            .map(h => h.innerText)
        """)

    async def get_ui_schema(self, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        return await page.evaluate("""
        () => {
            function visible(el) {
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && style.visibility !== 'hidden';
            }

            const elements = [];

            document.querySelectorAll("button, a, input, textarea, select").forEach(el => {
                if (!visible(el)) return;

                let tag = el.tagName.toLowerCase();
                let type = tag;
                let text = el.innerText || el.value || "";

                if (tag === "a") type = "link";

                if (tag === "input") {
                    type = el.type || "input";
                    text = el.placeholder || el.value || "";
                }

                elements.push({
                    type,
                    text: text.trim(),
                    placeholder: el.placeholder || null,
                    name: el.name || null,
                    id: el.id || null
                });
            });

            return elements;
        }
        """)

    # ---------------- FILE UPLOAD ---------------- #

    async def upload_file(self, selector: str, file_path: str, page_name: Optional[str] = None):
        page = await self.get_page(page_name)

        if not os.path.exists(file_path):
            return f"[ERROR] File not found: {file_path}"

        await page.set_input_files(selector, file_path)
        return f"[UPLOADED] {file_path}"

    async def upload_with_click(self, button_selector: str, file_path: str, page_name: Optional[str] = None):
        page = await self.get_page(page_name)

        async with page.expect_file_chooser() as fc:
            await page.click(button_selector)

        file_chooser = await fc.value
        await file_chooser.set_files(file_path)

        return f"[UPLOADED VIA BUTTON] {file_path}"

    # ---------------- LOGIN (LINKEDIN EXAMPLE) ---------------- #

    async def login_linkedin(self, page_name: Optional[str] = None):
        page = await self.get_page(page_name)

        try:
            await page.click("text=Sign in", timeout=self.max_timeout)
        except:
            await page.goto("https://www.linkedin.com/login")

        await page.fill("input[id='username']", os.getenv("LINKEDIN_USERNAME"))
        await page.fill("input[id='password']", os.getenv("LINKEDIN_PASSWORD"))
        await page.click("button[type='submit']")

        return "[LOGGED IN]"

from langchain.tools import tool


def build_tools(session, request_user_input, log_chat, misc_tools = False, file_tree_wrapper = None, base_path = None):
    """
    Create LangChain tools bound to a BrowserSession instance.

    The returned tools allow an agent to control a Playwright browser
    by opening pages, interacting with elements, reading content,
    and extracting structured information from the page.
    """

    @tool
    async def list_tabs() -> str:
        """
        List all open browser tabs.

        Returns:
            A list of tab names.
        """
        await log_chat("Listing tabs")
        try:
            return await session.list_tabs()
        except Exception as e:
            return f"{e}"
    @tool
    async def list_tabs_detailed() -> str:
        """
        List all open browser tabs with detailed information.

        Returns:
            A list of dictionaries with tab name, URL, and title.
        """
        await log_chat("Listing tabs detailed")
        try:
            return await session.list_tabs_detailed()
        except Exception as e:
            return f"{e}"
    
    @tool
    async def close_tab(name: str) -> str:
        """
        Close a specific browser tab.

        Args:
            name: Name of the tab to close.
        Returns:
            Confirmation message that the tab was closed.
        """
        await log_chat(f"Closing tab {name}")
        try:
            return await session.close_tab(name)
        except Exception as e:
            return f"{e}"
    
    @tool
    async def switch_tab(name: str) -> str:
        """
        Switch to a specific browser tab.

        Args:
            name: Name of the tab to switch to.
        Returns:
            Confirmation message that the tab was switched to.
        """
        await log_chat(f"Switching to tab {name}")
        try:
            return await session.switch_tab(name)
        except Exception as e:
            return f"{e}"
    
    @tool
    async def open_new_tab(url, page_name) -> str:
        """
        Open a new browser tab.
        Args:
            page_name: Name of the new tab.
            url: URL to open in the new tab.
        Returns:
            Confirmation message that a new tab was opened.
        """
        await log_chat("Opening new tab")
        try:
            return await session.new_page(page_name, url=url)
        except Exception as e:
            return f"{e}"

    @tool
    async def open_url(url: str, page_name: Optional[str] = None) -> str:
        """
        Navigate the browser to a specific URL.

        Args:
            url: The full URL to open.
            page_name: Optional name for the page. If not provided, uses the current page.
        Returns:
            Confirmation message that the page was opened.
        """
        await log_chat(f"Opening {url}")
        try:
            return await session.open_url(url, page_name)
        except Exception as e:
            await log_chat(f"Error opening {url}: {e}")
            return f"{e}"
        

    @tool
    async def click(selector: str, page_name: Optional[str] = None) -> str:
        """
        Click an element on the page.

        Args:
            selector: A Playwright-compatible selector such as
            'text=Login', '#submit', or 'button:has-text("Login")'.
            page_name: Optional name for the page. If not provided, uses the current page.
        Returns:
            Confirmation message indicating which element was clicked.
        """
        await log_chat(f"Clicking {selector}")
        try:
            return await session.click(selector, page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def type_text(selector: str, text: str, page_name: Optional[str] = None) -> str:
        """
        Type text into an input field.

        Args:
            selector: Selector identifying the input element.
            text: Text to type into the field.
            page_name: Optional name for the page. If not provided, uses the current page.

        Returns:
            Confirmation message of the typing action.
        """
        await log_chat(f"Typing {text} into {selector}")
        try:
            return await session.type_text(selector, text, page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def scroll(amount: int, page_name: Optional[str] = None) -> str:
        """
        Scroll the current page vertically.

        Args:
            amount: Number of pixels to scroll down.
            page_name: Optional name for the page. If not provided, uses the current page.
        Returns:
            Confirmation message indicating scroll distance.
        """
        await log_chat(f"Scrolling {amount}px")
        try:
            return await session.scroll(amount, page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_page_text(page_name: Optional[str] = None) -> str:
        """
        Retrieve all visible text from the page body.

        Useful when the agent needs to read or summarize page content.
        Args:
            page_name: Optional name for the page. If not provided, uses the current page.
        Returns:
            Full visible text of the webpage.
        """
        await log_chat("Getting page text")
        try:
            return await session.get_page_text(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_title(page_name: Optional[str] = None) -> str:
        """
        Get the title of the current webpage.

        Returns:
            The page title.
        """
        await log_chat("Getting page title")
        try:
            return await session.get_title(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_ui_schema(page_name: Optional[str] = None) -> list:
        """
        Extract structured UI elements from the page.

        This returns a simplified representation of interactive
        elements such as buttons, links, and input fields.
        Useful for browser agents to understand what actions
        are possible on the page.
        Args: 
            page_name: Optional name for the page. If not provided, uses the current page.
        Returns:
            A list of UI element dictionaries.
        """
        await log_chat("Getting UI schema")
        try:
            return await session.get_ui_schema(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_all_links(page_name: Optional[str] = None) -> list:
        """
        Extract all hyperlinks from the page.
        Arge:
            page_name: Optional name for the page. If not provided, uses the current page.
        Returns:
            A list of URLs found in anchor tags.
        """
        await log_chat("Getting all links")
        try:
            return await session.get_all_links(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_all_headings(page_name: Optional[str] = None) -> list:
        """
        Extract all headings from the page.

        This includes H1 through H6 elements.
        Args:
            page_name: Optional name for the page. If not provided, uses the current page.
        Returns:
            A list of heading texts.
        """
        await log_chat("Getting all headings")
        try:
            return await session.get_all_headings(page_name)
        except Exception as e:
            return f"{e}"

    # @tool
    # async def login() -> str:
    #     """
    #     Login to the current page.

    #     Returns:
    #         Confirmation message indicating login status.
    #     """
    #     print("Logging in")
    #     try:
    #         return await session.login()
    #     except Exception as e:
    #         return f"{e}"

    @tool
    async def submit_form(page_name) -> str:
        """
        Submit the current form.
        Args:
            page_name: Optional name for the page. If not provided, uses the current page.  
        Returns:
            Confirmation message indicating form submission status.
        """
        await log_chat("Submitting form")
        try:
            return await session.submit_form(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def fill_any_form(form_elements: List[Dict[str, str]], page_name) -> str:
        """
        Args:
        form_elements: List of form elements to fill.
            Fill multiple form fields on the current page.

            Each element:
            - selector: CSS selector
            - value: value to type (optional)

            If value is missing or empty, user will be prompted.
        page_name: Optional name for the page. If not provided, uses the current page.
        Returns:
            Confirmation message indicating form fill status.
        """

        results = []
        errors = []
        await log_chat("Filling form")
        await log_chat(f"Form elements: {form_elements}")
        for element in form_elements:
            try:
                selector = element.get("selector")
                value = element.get("value")

                if not selector:
                    errors.append("Missing selector in one of the fields")
                    continue

                # ask always
                
                value = await request_user_input(
                    f"Enter value for field: {selector} : {value}"
                )
                await log_chat(f"Value: {value}")
                if value == "null" or value == "undefined" or value.strip() == "":
                    value = element.get("value")

                # Optional: clear before typing
                try:
                    await log_chat(f"Clearing {selector}")
                    await session.clear(selector, page_name)
                except:
                    await log_chat(f"Failed to clear {selector}")
                    pass
                
                await log_chat(f"Typing {value} into {selector}")
                await session.type_text(selector, value, page_name)
                results.append(selector)

            except Exception as e:
                errors.append(f"{selector}: {str(e)}")

        # -------------------------------
        # RESPONSE
        # -------------------------------
        response_parts = []

        if results:
            response_parts.append(f"Filled: {', '.join(results)}")

        if errors:
            response_parts.append(f"Errors: {' | '.join(errors)}")
        else:
            await session.submit_form() # 🔥 Submit form

        return " | ".join(response_parts)
    
    @tool
    async def get_user_confirmation(query: str) -> str:
        """
        Get user input.

        Args:
            query: Query to ask the user.

        Returns:
            User input ("true" or "false").
        """
        await log_chat(f"Getting user input for {query}")
        try:
            user_response =  await request_user_input(query + " (yes/no)")
            if user_response == "null" or user_response == "undefined" or user_response.strip() == "":
                return "User did not provide a response."
            
            if "yes" in user_response.lower():
                return "true"
            elif "no" in user_response.lower():
                return "false"
            else:
                return user_response
        except Exception as e:
            return f"{e}"
        
    @tool
    async def get_all_links_with_text(page_name: Optional[str] = None) -> list:
        """
        Extract all hyperlinks from the page with their text.
        Args:
            page_name: Optional name for the page. If not provided, uses the current page.
        Returns:
            A list of dictionaries with text and href.
        """
        await log_chat("Getting all links with text")
        try:
            return await session.get_all_links_with_text()
        except Exception as e:
            return f"{e}"
        
    # -------------------------------
    # HELPERS (ADD ONCE)
    # -------------------------------
    def get_user_files_dir(base_path = base_path):
        base = os.path.join(base_path, "files")
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

    def get_user_memory_path():
        base = get_user_files_dir()
        os.makedirs(base, exist_ok=True)
        if not os.path.exists(os.path.join(base, "url_memory.json")):
            with open(os.path.join(base, "url_memory.json"), "w") as f:
                f.write("{}")
        return os.path.join(base, "url_memory.json")

    # -------------------------------
    # GET FILE TREE
    # -------------------------------
    @tool
    async def get_all_files():
        """
        Get a list of all files in the user's files directory.

        Returns:
            A list of dictionaries with file information.
        """
        await log_chat("Getting full file tree")

        try:
            base_dir = get_user_files_dir()
            nodes = []

            for root, dirs, files in os.walk(base_dir):

                for d in dirs:
                    full_path = os.path.join(root, d)
                    rel = os.path.relpath(full_path, base_dir)

                    nodes.append({
                        "name": d,
                        "path": full_path,
                        "project_path": f"files/{rel.replace(os.sep, '/')}",
                        "type": "folder"
                    })

                for f in files:
                    full_path = os.path.join(root, f)
                    rel = os.path.relpath(full_path, base_dir)

                    nodes.append({
                        "name": f,
                        "path": full_path,
                        "project_path": f"files/{rel.replace(os.sep, '/')}",
                        "type": "file"
                    })

            return {"nodes": nodes}

        except Exception as e:
            await log_chat(f"Error getting files: {e}")
            return {"error": str(e)}


    # -------------------------------
    # SAVE FILE
    # -------------------------------
    @tool
    async def save_to_file(content: str, filename: str) -> str:
        """
        Save content to a file.

        Args:
            content: Content to save.
            filename: Name of the file.

        Returns:
            Confirmation message.
        """
        await log_chat(f"Saving file: {filename}")

        if not filename.startswith("files/"):
            return "Invalid filename. Must start with 'files/'"

        try:
            full_path = resolve_user_path(filename)

            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            tmp_path = full_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)

            os.replace(tmp_path, full_path)

            if file_tree_wrapper:
                await file_tree_wrapper()

            return f"Saved to {filename}"

        except Exception as e:
            await log_chat(f"Save error: {e}")
            return str(e)


    # -------------------------------
    # READ FILE
    # -------------------------------
    @tool
    async def read_file(filepath: str) -> str:
        """
        Read the content of a file.

        Args:
            filepath: Path of the file.

        Returns:
            Content of the file.
        """
        await log_chat(f"Reading file: {filepath}")

        try:
            full_path = resolve_user_path(filepath)

            if not os.path.exists(full_path):
                return f"File not found: {filepath}"

            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()

        except Exception as e:
            return str(e)


    # -------------------------------
    # DELETE FILE
    # -------------------------------
    @tool
    async def delete_file(filepath: str) -> str:
        """
        Delete a file.

        Args:
            filepath: Path of the file.

        Returns:
            Confirmation message.
        """
        await log_chat(f"Deleting file: {filepath}")

        if not filepath.startswith("files/"):
            return "Invalid filepath"

        try:
            full_path = resolve_user_path(filepath)

            if not os.path.exists(full_path):
                return f"File not found: {filepath}"

            if os.path.isdir(full_path):
                return "Path is a directory, not a file"

            confirm = await get_user_confirmation(f"Delete {filepath}?")
            if "true" not in confirm.lower():
                return "Cancelled by user"

            os.remove(full_path)

            if file_tree_wrapper:
                await file_tree_wrapper()

            return f"Deleted {filepath}"

        except Exception as e:
            await log_chat(f"Delete error: {e}")
            return str(e)


    # -------------------------------
    # CREATE DIRECTORY
    # -------------------------------
    @tool
    async def create_directory(dirname: str) -> str:
        """
        Create a directory.

        Args:
            dirname: Name of the directory.

        Returns:
            Confirmation message.
        """
        await log_chat(f"Creating directory: {dirname}")

        if not dirname.startswith("files/"):
            return "Invalid directory name"

        try:
            dir_path = resolve_user_path(dirname)

            if os.path.exists(dir_path):
                return "Directory already exists"

            os.makedirs(dir_path, exist_ok=True)

            if file_tree_wrapper:
                await file_tree_wrapper()

            return f"Created {dirname}"

        except Exception as e:
            return str(e)


    # -------------------------------
    # DELETE DIRECTORY
    # -------------------------------
    @tool
    async def delete_directory(dirname: str) -> str:
        """
        Delete a directory.

        Args:
            dirname: Name of the directory.

        Returns:
            Confirmation message.
        """
        await log_chat(f"Deleting directory: {dirname}")

        if not dirname.startswith("files/"):
            return "Invalid directory name"

        try:
            dir_path = resolve_user_path(dirname)

            if not os.path.exists(dir_path):
                return "Directory not found"

            shutil.rmtree(dir_path)

            if file_tree_wrapper:
                await file_tree_wrapper()

            return f"Deleted {dirname}"

        except Exception as e:
            return str(e)


    # -------------------------------
    # MOVE FILE
    # -------------------------------
    @tool
    async def move_file(src: str, dst: str) -> str:
        """
        Move a file.

        Args:
            src: Source path.
            dst: Destination path.

        Returns:
            Confirmation message.
        """
        await log_chat(f"Moving file: {src} → {dst}")

        if not src.startswith("files/") or not dst.startswith("files/"):
            return "Invalid paths"

        try:
            src_path = resolve_user_path(src)
            dst_path = resolve_user_path(dst)

            if not os.path.exists(src_path):
                return "Source not found"

            if os.path.exists(dst_path):
                return "Destination already exists"

            os.makedirs(os.path.dirname(dst_path), exist_ok=True)

            shutil.move(src_path, dst_path)

            if file_tree_wrapper:
                await file_tree_wrapper()

            return f"Moved {src} → {dst}"

        except Exception as e:
            await log_chat(f"Move error: {e}")
            return str(e)
    @tool
    async def get_user_input_from_options(options: str) -> str:
        """
        Get user input from a list of options.

        Args:
            options: List of options.
            
        Returns:
            User selected option.
        
        Example:
            options: 1. Red, 2. Green, 3. Blue
            returns: 2
        """
        await log_chat("Getting user input from options")
        try:
            user_response =  await request_user_input(
                f"Select an option: {options}"
            )
            return user_response
        except Exception as e:
            return f"{e}"
    
    


    @tool
    async def convert_md(filepath: str, output_type: str, output_filename: str) -> str:
        """
            Convert a Markdown file to PDF or DOCX.

            Args:
                filepath: Path to the Markdown file.
                output_type: Type of output file (pdf, docx).
                output_filename: Name of the output file with extension.
        
        """
        await log_chat(f"Converting {filepath} → {output_type}")

        try:
            # -------------------------
            # VALIDATIONS
            # -------------------------
            if output_type not in ("pdf", "docx"):
                return "Invalid output type. Supported: pdf, docx"

            if not os.path.exists(filepath):
                return f"File not found: {filepath}"

            if not output_filename.lower().endswith(f".{output_type}"):
                return "Output filename does not match output type"

            os.makedirs("files", exist_ok=True)

            output_path = os.path.join("files", output_filename)

            # -------------------------
            # ENSURE PANDOC EXISTS
            # -------------------------
            try:
                pypandoc.get_pandoc_version()
            except:
                await log_chat("Pandoc not found. Downloading...")
                pypandoc.download_pandoc()

            # -------------------------
            # CONVERSION
            # -------------------------
            extra_args = ["--standalone"]

            if output_type == "pdf":
                extra_args.append("--pdf-engine=xelatex")  # better rendering

            pypandoc.convert_file(
                filepath,
                output_type,
                outputfile=output_path,
                extra_args=extra_args
            )

            return f"Conversion successful: {output_path}"

        except Exception as e:
            await log_chat(f"Error converting file: {e}")
            return f"Failed to convert: {str(e)}"

    @tool
    async def upload_file(selector: str, file_path: str) -> str:
        """
        Upload a file to an input field.

        Args:
            selector: Selector for file input (e.g. input[type="file"])
            file_path: Path to the file

        Returns:
            Confirmation message
        """
        await log_chat(f"Uploading file {file_path} → {selector}")
        try:
            return await session.upload_file(selector, file_path)
        except Exception as e:
            return f"{e}"

    @tool
    async def upload_with_click(button_selector: str, file_path: str) -> str:
        """
        Upload a file by clicking a button.

        Args:
            button_selector: Selector for the button
            file_path: Path to the file

        Returns:
            Confirmation message
        """
        await log_chat(f"Uploading file {file_path} → {button_selector}")
        try:
            return await session.upload_with_click(button_selector, file_path)
        except Exception as e:
            return f"{e}"

    @tool
    async def update_memory(url: str, reason: str, observation: str) -> str:
        """
        Update the URL memory with a new observation.
        """

        await log_chat(f"Updating memory for url {url}")

        try:
            file_path = get_user_memory_path()

            memory = {}

            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        memory = json.load(f)
                except json.JSONDecodeError:
                    memory = {}

            if url in memory:
                memory[url].append({
                    "reason": reason,
                    "observation": observation
                })
            else:
                memory[url] = [{
                    "reason": reason,
                    "observation": observation
                }]

            # 🔥 atomic write (safe)
            tmp_path = file_path + ".tmp"

            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(memory, f, indent=4)

            os.replace(tmp_path, file_path)

            return "Memory updated successfully."

        except Exception as e:
            await log_chat(f"Memory error: {e}")
            return str(e)

    @tool
    async def read_memory() -> str:
        """
        Read the URL memory.
        """
        await log_chat("Reading memory")

        try:
            file_path = get_user_memory_path()

            if not os.path.exists(file_path):
                return "{}"

            with open(file_path, "r", encoding="utf-8") as f:
                memory = json.load(f)

            return json.dumps(memory, indent=2)

        except Exception as e:
            return str(e)
        
    @tool
    async def clear_memory() -> str:
        """
        Clear the URL memory.
        """
        await log_chat("Clearing memory")

        try:
            file_path = get_user_memory_path()

            if not os.path.exists(file_path):
                return "Memory already empty"

            os.remove(file_path)

            return "Memory cleared successfully."

        except Exception as e:
            return str(e)

    @tool
    async def get_current_date_time() -> str:
        """
        Get the current date and time.
        """
        await log_chat("Getting current date and time")
        try:
            return datetime.datetime.now().strftime("%A, %d %B %Y %H:%M:%S")
        except Exception as e:
            return str(e)


    misc_tools_list = [
        get_user_confirmation,
        get_all_files,
        save_to_file,
        get_user_input_from_options,
        read_file,
        convert_md,
        delete_file,
        create_directory,
        move_file,
        delete_directory,
        update_memory,
        read_memory,
        clear_memory,
        get_current_date_time
        
    ]

    browser_tools = [
        open_url,
        click,
        type_text,
        scroll,
        get_page_text,
        get_title,
        get_ui_schema,
        get_all_links,
        get_all_headings,
        submit_form,
        fill_any_form,
        get_all_links_with_text,
        upload_file,
        upload_with_click,
        list_tabs,
        list_tabs_detailed,
        close_tab,
        switch_tab
    ]

    if misc_tools:
        return misc_tools_list
    else:
        return browser_tools + misc_tools_list
