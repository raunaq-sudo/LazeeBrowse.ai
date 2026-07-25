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
from rich import print
import datetime
# from langchain_community.document_loaders import RecursiveUrlLoader
from bs4 import BeautifulSoup
import re
from typing import Dict, Optional
from langchain.tools import tool
# from rank_bm25 import BM25Okapi
# ---------------- BM25 ---------------- #

# class BM25Index:
#     def __init__(self):
#         self.docs = []
#         self.tokenized = []
#         self.bm25 = None

#     def add_documents(self, documents):
#         for doc in documents:
#             tokens = doc["text"].lower().split()
#             self.docs.append(doc)
#             self.tokenized.append(tokens)

#         self.bm25 = BM25Okapi(self.tokenized)

#     def search(self, query, k=5):
#         tokens = query.lower().split()
#         scores = self.bm25.get_scores(tokens)

#         ranked = sorted(
#             zip(self.docs, scores),
#             key=lambda x: x[1],
#             reverse=True
#         )

#         return [
#             {
#                 "text": doc["text"],
#                 "score": float(score),
#                 "source": doc.get("source")
#             }
#             for doc, score in ranked[:k]
#         ]


# ---------------- MAIN ---------------- #

def build_tools(session, request_user_input, log_chat, misc_tools = False, only_browser_tools = False, file_tree_wrapper = None, base_path = None):
    """
    Create LangChain tools bound to a BrowserSession instance.

    The returned tools allow an agent to control a Playwright browser
    by opening pages, interacting with elements, reading content,
    and extracting structured information from the page.
    """

    def bs4_extractor(html: str):
        soup = BeautifulSoup(html, "lxml")

        # ❌ Remove unwanted tags
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
            tag.decompose()

        elements = soup.find_all(["h1", "h2", "h3", "p", "a", "li", "input"])

        results = []

        for el in elements:
            text = el.get_text(separator=" ", strip=True)

            # ❌ Skip empty
            if not text:
                continue

            # ❌ Normalize whitespace
            text = re.sub(r"[ \t]+", " ", text)

            # ❌ Skip UI labels
            if text.lower() in {
                "world news", "politics news", "view more", "in focus"
            }:
                continue

            # ❌ Skip timestamps
            if re.search(r"\b\d{1,2}:\d{2}\s?(AM|PM)\b", text):
                continue

            # ❌ Skip dates
            if re.search(r"\b[A-Za-z]+\s\d{1,2},\s\d{4}\b", text):
                continue

            # ❌ Skip short junk
            if len(text) < 40:
                continue

            result = {
                "text": text,
                "tag": el.name,
                "id": el.get("id"),
                "name": el.get("name"),
                "href": el.get("href") if el.name == "a" else None
            }

            results.append(result)

        return json.dumps(results)


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
    
    from urllib.parse import urlparse

    def get_base_url(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    # @tool
    # async def scrape_url(url: str, query: str):
    #     """
    #         This tool is used to scrape the website and return relevant information inline with the query.
    #         Args:
    #             url:str -> this is the url of the website needed for scrapping.
    #             query:str -> this is the query that needs to be answered to.
            
    #         Response:
    #             returns list of relevant sections of the webpage.
        
    #     """
    #     await log_chat(f"Scrapping tool called for query {query} on url {url}")
    #     def is_error_page(doc):
    #         text = doc.page_content.lower()
    #         return (
    #             "an error occurred" in text or
    #             "reference #" in text or
    #             "edgesuite.net" in text
    #         )

    #     def fix_url(url: str) -> str:
    #         if not url:
    #             return url
    #         if "http" in url[8:]:
    #             return url[url.find("http", 8):]
    #         return url

    #     loader = RecursiveUrlLoader(
    #         url,
    #         extractor=bs4_extractor,  # returns JSON string
    #         use_async=True,
    #         max_depth=3,  # 🔥 reduce depth (5 is too aggressive)
    #         headers={
    #             "User-Agent": "Mozilla/5.0",
    #             "Accept": "text/html"
    #         },
    #         prevent_outside=True,
    #         base_url=get_base_url(url)
    #     )

    #     documents = []

    #     async for doc in loader.alazy_load():

    #         source = fix_url(doc.metadata.get("source"))

    #         if not source.startswith("http"):
    #             continue

    #         if is_error_page(doc):
    #             continue

    #         try:
    #             # ✅ parse JSON from extractor
    #             structured = json.loads(doc.page_content)
    #         except:
    #             continue

    #         for item in structured:
    #             text = item.get("text", "").strip()

    #             if not text or len(text) < 40:
    #                 continue

    #             documents.append({
    #                 "text": text,
    #                 "source": source,
    #                 "tag": item.get("tag"),
    #                 "href": item.get("href")
    #             })

    #     # ✅ Deduplicate
    #     seen = set()
    #     unique_docs = []

    #     for doc in documents:
    #         if doc["text"] in seen:
    #             continue
    #         seen.add(doc["text"])
    #         unique_docs.append(doc)
    #     print(documents)
    #     # ✅ BM25
    #     bm25 = BM25Index()
    #     bm25.add_documents(unique_docs)

    #     response =  bm25.search(query, k=5)
    #     print("BM25\n\n")
    #     print(response)
    #     if len(response)>0:
    #         return response
    #     print("Nothing could be found that matches your query.")
    #     return "Nothing could be found that matches your query."



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
    async def search_url(page_name:str, query:str) -> str:
        """
        This tool is intended to search the website if a search bar is present.

        Args:
            page_name: str -> Name of the page on which the search is to be performed.
            query: str -> query to be searched.
        
        Returns:
            ui_schema of the visible section. 
        
        
        """
        log_chat("Searching URL.")
        try:
            return await session.search_url(page_name, query)
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
    async def find_tab_by_url(keyword:str) -> str:
        """
        Get tab name based on keywords in the url.
        Args:
            keyword: keyword to be searched in the urls of all tabs
        Returns:
            page_name if present.
        """
        await log_chat(f"Searching for tab based on url:{keyword}")
        try:
            return await session.find_tab_by_url(keyword)
        except Exception as e:
            print(f"Exception in searching for keyword in Url : {str(e)}")
            return str(e)


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
            response = await session.open_url(url, page_name)
            return await session.get_ui_schema(page_name, 'visible')
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
            Confirmation message that the element was clicked.    
         """
        # A json object containing the changes in the UI before and after the click.
            
        #     "page_before_event": Ui elements before the click 
        #     "page_after_event": Ui elements after the click 
        #     "common_elements": Common elements
        await log_chat(f"Clicking {selector}")
        try:
            # previous_schema = await session.get_ui_schema(page_name)
            response =  await session.click(selector, page_name)
            # new_schema = await session.get_ui_schema(page_name)
            return response
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
    async def get_visible_modal_schema(page_name: Optional[str] = None) -> list:
        """
        Get the visible modal schema of the current page.
        Args:
            page_name: Optional name for the page. If not provided, uses the current page.
        Returns:
            A list of modal element dictionaries.
        """
        await log_chat("Getting visible modal schema")
        try:
            return await session.get_visible_modal_schema(page_name)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_ui_schema(page_name: Optional[str] = None, mode: str = None) -> list:
        """
        Extract a structured UI schema from the current browser page.

        Returns a hierarchical representation of visible and interactive elements,
        including regions (e.g., modal, overlay, page) and their element trees.

        Modes:
        - "visible": Only elements currently visible in the viewport (default; best for actions).
        - "interactive": Includes visible + hidden but relevant UI (modals, dropdowns).
        - "full": Entire DOM (for indexing/RAG; not recommended for interaction).

        Each element contains metadata such as tag, text, selector, fingerprint,
        confidence score, action hint, state (enabled/clickable), and layout (position, size, z-index).

        Used for UI understanding, element selection, and browser automation workflows.
        """
        await log_chat("Getting UI schema")
        try:
            schema =  await session.get_ui_schema(page_name, mode)
            return schema
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
        # A json object containing the changes in the UI before and after the form submission.
            
        #     "page_before_event": Ui elements before the submission
        #     "page_after_event": Ui elements after the submission
        #     "common_elements": Common elements
        await log_chat("Submitting form")
        try:
            # previous_schema = await session.get_ui_schema(page_name)
            response = await session.submit_form(page_name)
            # new_schema = await session.get_ui_schema(page_name)
            return response
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
        # await log_chat(f"Form elements: {form_elements}")
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
                # await log_chat(f"Value: {value}")
                if value == "null" or value == "undefined" or value.strip() == "":
                    value = element.get("value")

                # Optional: clear before typing
                try:
                    # await log_chat(f"Clearing {selector}")
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
            await session.submit_form(page_name) # 🔥 Submit form

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
        await log_chat(f"Getting user input.")
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
            return await session.get_all_links_with_text(page_name)
        except Exception as e:
            return f"{e}"
        
    # -------------------------------
    # HELPERS (ADD ONCE)
    # -------------------------------
    def get_user_files_dir():
        return _get_user_files_dir(base_path)

    def _get_user_files_dir(base_path = base_path):
        base = os.path.join(base_path, "files")
        os.makedirs(base, exist_ok=True)
        return base


    def resolve_user_path(relative_path: str):
        base = get_user_files_dir()
        print(f"Resolving user path: {relative_path}")
        print(f"Base: {base}")
        clean = os.path.normpath(relative_path).lstrip(os.sep)
        print(f"Clean: {clean}")
        full_path = os.path.join(base, clean)
        print(f"Full path: {full_path}")
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


    def flatten_ui_schema(schema):
        flat = []

        # Page elements
        for el in schema.get("page", []):
            flat.append({**el, "context": "page"})

        # Modal elements
        for i, modal in enumerate(schema.get("modals", [])):
            for el in modal.get("elements", []):
                flat.append({
                    **el,
                    "context": f"modal_{i}"
                })

        return flat

    def diff_ui_schemas(schema1, schema2):
        """
        Compare two UI schema lists and return differences.

        Returns:
        {
            "only_in_schema1": [...],
            "only_in_schema2": [...],
            "common": [...]
        }
        """
        schema1 = flatten_ui_schema(schema1)
        schema2 = flatten_ui_schema(schema2)
        def normalize(el):
            """Create a stable comparison key"""
            return (
                el.get("type"),
                (el.get("text") or "").strip(),
                el.get("placeholder"),
                el.get("name"),
                el.get("id"),
            )

        set1 = {normalize(el): el for el in schema1}
        set2 = {normalize(el): el for el in schema2}

        keys1 = set(set1.keys())
        keys2 = set(set2.keys())

        only_1_keys = keys1 - keys2
        only_2_keys = keys2 - keys1
        common_keys = keys1 & keys2

        return {
            "page_before_event": [set1[k] for k in only_1_keys],
            "page_after_event": [set2[k] for k in only_2_keys],
            "common_elements": [set1[k] for k in common_keys],
        }
    

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
            if file_tree_wrapper:
                # await log_chat("Using file tree wrapper")
                return await file_tree_wrapper()
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
    async def write_file(content: str, filename: str) -> str:
        """
        Save content to a file.

        Args:
            content: Content to save.
            filename: Name of the file.

        Returns:
            Confirmation message.
        """
        await log_chat(f"Saving file: {filename}")

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

    @tool
    async def amend_file(content: str, filename: str) -> str:
        """
        Amend content to a file.

        Args:
            content: Content to save.
            filename: Name of the file.

        Returns:
            Confirmation message.
        """
        await log_chat(f"Amending file: {filename}")
        try:
            full_path = resolve_user_path(filename)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "a", encoding="utf-8") as f:
                f.write(content)

            if file_tree_wrapper:
                await file_tree_wrapper()

            return f"Amended {filename}"
        except Exception as e:
            await log_chat(f"Amend error: {e}")
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

        # if not filepath.startswith("files/"):
        #     return "Invalid filepath"

        try:
            full_path = resolve_user_path(filepath)
            await log_chat(f"Full path: {full_path}")
            if not os.path.exists(full_path):
                return f"File not found: {filepath}"

            if os.path.isdir(full_path):
                return "Path is a directory, not a file"

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
        try:
            dir_path = resolve_user_path(dirname)

            if not os.path.exists(dir_path):
                return "Directory not found"

            shutil.rmtree(dir_path)

            if file_tree_wrapper:
                await file_tree_wrapper()

            return f"Deleted {dirname}"

        except Exception as e:
            print(str(e))
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
    async def rename_file(src: str, dst: str) -> str:
        """
        Rename a file.

        Args:
            src: Source path.
            dst: Destination path.

        Returns:
            Confirmation message.
        """
        await log_chat(f"Renaming file: {src} → {dst}")
        try:
            src_path = resolve_user_path(src)
            dst_path = resolve_user_path(dst)
            if not os.path.exists(src_path):
                return "Source not found"
            os.rename(src_path, dst_path)
            if file_tree_wrapper:
                await file_tree_wrapper()
            return f"Renamed {src} → {dst}"
        except Exception as e:
            await log_chat(f"Rename error: {e}")
            return str(e)
    
    @tool
    async def rename_folder(src: str, dst: str) -> str:
        """
        Rename a folder.

        Args:
            src: Source path.
            dst: Destination path.

        Returns:
            Confirmation message.
        """
        await log_chat(f"Renaming folder: {src} → {dst}")
        try:
            src_path = resolve_user_path(src)
            dst_path = resolve_user_path(dst)
            if not os.path.exists(src_path):
                return "Source not found"
            os.rename(src_path, dst_path)
            if file_tree_wrapper:
                await file_tree_wrapper()
            return f"Renamed {src} → {dst}"
        except Exception as e:
            await log_chat(f"Rename error: {e}")
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


    @tool
    async def action_logger(action:str)->str:
        """
        Use this tool to send your action to the user.
        Args:
            action: the action taken or you are about to take
        Response:
            success message
        """
        try:
            await log_chat(action)
            return "Success"
        except Exception as e:
            print(f"Error in action logger.")
            return "Error. Please try again."


    misc_tools_list = [
        get_user_confirmation,
        get_all_files,
        write_file,
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
        get_current_date_time,
        rename_file,
        rename_folder,
        amend_file,
        action_logger
        
    ]

    browser_tools = [
        open_url,
        open_new_tab,
        click,
        type_text,
        scroll,
        get_page_text,
        get_title,
        get_ui_schema,
        get_visible_modal_schema,
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
        switch_tab,
        search_url,
        find_tab_by_url
    ]

    misc_tools_imp = [
        get_user_confirmation,
        get_current_date_time,
        move_file,
        delete_file,
        delete_directory,
        get_user_input_from_options
    ]


    if misc_tools:
        return misc_tools_list
    elif only_browser_tools:
        return browser_tools + misc_tools_list
    else:
        return browser_tools + misc_tools_list
