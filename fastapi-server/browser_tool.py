import asyncio
from dotenv import load_dotenv
load_dotenv()
import os
import time
import shutil
from typing import List, Dict

import pypandoc
   
class BrowserSession:

    def __init__(self, page):
        self.page = page
        self.max_timeout = 5000

    async def open_url(self, url: str):
        await self.page.goto(url, timeout=self.max_timeout)
        time.sleep(1)
        await self.page.mouse.click(0,200)
        return f"Opened {url}"

    async def click(self, selector: str):
        await self.page.click(selector)
        return f"Clicked {selector}"

    async def type_text(self, selector: str, text: str):
        await self.clear(selector)
        await self.page.type(selector, text)
        return f"Typed '{text}' into {selector}"

    async def scroll(self, amount: int = 1000):
        await self.page.mouse.wheel(0, amount)
        return f"Scrolled {amount}px"

    async def get_page_text(self):
        return await self.page.inner_text("body")

    async def get_title(self):
        return await self.page.title()

    async def submit_form(self):
        await self.page.keyboard.press("Enter")
        return f"Form submited."

    async def login(self):
        try:
            await self.page.click("text=Sign in", timeout=self.max_timeout)
        except Exception as e:
            print(f"Error clicking sign in: {e}")
            await self.open_url("https://www.linkedin.com/login?fromSignIn=true&trk=guest_homepage-basic_nav-header-signin")
            pass
        try:
            await self.page.fill("input[id='username']", os.getenv("LINKEDIN_USERNAME"), timeout=self.max_timeout)
        except Exception as e:
            print(f"Error typing username: {e}")
            try:
                await self.page.fill("input[id='email-or-phone']", os.getenv("LINKEDIN_USERNAME"), timeout=self.max_timeout)
            except Exception as e:
                print(f"Error typing username: {e}")
                pass

        try:
            await self.page.fill("input[id='password']", os.getenv("LINKEDIN_PASSWORD"), timeout=self.max_timeout)
        except Exception as e:
            print(f"Error typing password: {e}")
            pass
        try:
            await self.page.click("button[type='submit']", timeout=self.max_timeout)
        except Exception as e:
            print(f"Error clicking submit: {e}")
            pass
        return "Logged in"

    async def get_ui_schema(self):
        return await self.page.evaluate("""
        () => {

            function visible(el) {
                const style = window.getComputedStyle(el);
                return style && style.display !== 'none' && style.visibility !== 'hidden';
            }

            const elements = [];

            document.querySelectorAll("button, a, input, textarea, select").forEach(el => {

                if (!visible(el)) return;

                const tag = el.tagName.toLowerCase();

                let type = tag;
                let text = el.innerText || el.value || "";

                if (tag === "a") type = "link";

                if (tag === "input") {
                    type = el.type || "input";
                    text = el.placeholder || el.value || "";
                }

                elements.push({
                    type: type,
                    text: text.trim(),
                    placeholder: el.placeholder || null,
                    name: el.name || null,
                    id: el.id || null
                });

            });

            return elements;

        }
        """)

    async def get_all_links(self):
        return await self.page.evaluate("""
        () => {
            const links = [];
            document.querySelectorAll("a").forEach(el => {
                links.push(el.href);
            });
            return links;
        }
        """)

    async def get_all_headings(self):
        return await self.page.evaluate("""
        () => {
            const headings = [];
            document.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach(el => {
                headings.push(el.innerText);
            });
            return headings;
        }
        """)
    
    async def clear(self, selector: str):
        await self.page.fill(selector, "")
        return f"Cleared {selector}"
    
    async def get_all_links_with_text(self):
        return await self.page.evaluate("""
        () => {
            const links = [];
            document.querySelectorAll("a").forEach(el => {
                links.push({text: el.innerText, href: el.href});
            });
            return links;
        }
        """)
    
    async def upload_file(self, selector: str, file_path: str) -> str:

        if not os.path.exists(file_path):
            return f"File not found: {file_path}"

        try:
            await self.page.set_input_files(selector, file_path)
            return f"Uploaded {file_path} to {selector}"
        except Exception as e:
            return f"Upload failed: {str(e)}"

    async def upload_with_click(self, button_selector: str, file_path: str) -> str:

        async with self.page.expect_file_chooser() as fc:
            await self.page.click(button_selector)

        file_chooser = await fc.value
        await file_chooser.set_files(file_path)

        return f"Uploaded {file_path} via button"
    

from langchain.tools import tool


def build_tools(session, request_user_input, log_chat, misc_tools = False):
    """
    Create LangChain tools bound to a BrowserSession instance.

    The returned tools allow an agent to control a Playwright browser
    by opening pages, interacting with elements, reading content,
    and extracting structured information from the page.
    """

    @tool
    async def open_url(url: str) -> str:
        """
        Navigate the browser to a specific URL.

        Args:
            url: The full URL to open.

        Returns:
            Confirmation message that the page was opened.
        """
        await log_chat(f"Opening {url}")
        try:
            return await session.open_url(url)
        except Exception as e:
            return f"{e}"

    @tool
    async def click(selector: str) -> str:
        """
        Click an element on the page.

        Args:
            selector: A Playwright-compatible selector such as
            'text=Login', '#submit', or 'button:has-text("Login")'.

        Returns:
            Confirmation message indicating which element was clicked.
        """
        await log_chat(f"Clicking {selector}")
        try:
            return await session.click(selector)
        except Exception as e:
            return f"{e}"

    @tool
    async def type_text(selector: str, text: str) -> str:
        """
        Type text into an input field.

        Args:
            selector: Selector identifying the input element.
            text: Text to type into the field.

        Returns:
            Confirmation message of the typing action.
        """
        await log_chat(f"Typing {text} into {selector}")
        try:
            return await session.type_text(selector, text)
        except Exception as e:
            return f"{e}"

    @tool
    async def scroll(amount: int) -> str:
        """
        Scroll the current page vertically.

        Args:
            amount: Number of pixels to scroll down.

        Returns:
            Confirmation message indicating scroll distance.
        """
        await log_chat(f"Scrolling {amount}px")
        try:
            return await session.scroll(amount)
        except Exception as e:
            return f"{e}"

    @tool
    async def get_page_text() -> str:
        """
        Retrieve all visible text from the page body.

        Useful when the agent needs to read or summarize page content.

        Returns:
            Full visible text of the webpage.
        """
        await log_chat("Getting page text")
        try:
            return await session.get_page_text()
        except Exception as e:
            return f"{e}"

    @tool
    async def get_title() -> str:
        """
        Get the title of the current webpage.

        Returns:
            The page title.
        """
        await log_chat("Getting page title")
        try:
            return await session.get_title()
        except Exception as e:
            return f"{e}"

    @tool
    async def get_ui_schema() -> list:
        """
        Extract structured UI elements from the page.

        This returns a simplified representation of interactive
        elements such as buttons, links, and input fields.
        Useful for browser agents to understand what actions
        are possible on the page.

        Returns:
            A list of UI element dictionaries.
        """
        await log_chat("Getting UI schema")
        try:
            return await session.get_ui_schema()
        except Exception as e:
            return f"{e}"

    @tool
    async def get_all_links() -> list:
        """
        Extract all hyperlinks from the page.

        Returns:
            A list of URLs found in anchor tags.
        """
        await log_chat("Getting all links")
        try:
            return await session.get_all_links()
        except Exception as e:
            return f"{e}"

    @tool
    async def get_all_headings() -> list:
        """
        Extract all headings from the page.

        This includes H1 through H6 elements.

        Returns:
            A list of heading texts.
        """
        await log_chat("Getting all headings")
        try:
            return await session.get_all_headings()
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
    async def submit_form() -> str:
        """
        Submit the current form.

        Returns:
            Confirmation message indicating form submission status.
        """
        await log_chat("Submitting form")
        try:
            return await session.submit_form()
        except Exception as e:
            return f"{e}"

    @tool
    async def fill_any_form(form_elements: List[Dict[str, str]]) -> str:
        """
        Fill multiple form fields on the current page.

        Each element:
        - selector: CSS selector
        - value: value to type (optional)

        If value is missing or empty, user will be prompted.
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

                if value == "null" or value == "undefined" or value.strip() == "":
                    value = element.get("value")

                # Optional: clear before typing
                try:
                    await log_chat(f"Clearing {selector}")
                    await session.clear(selector)
                except:
                    await log_chat(f"Failed to clear {selector}")
                    pass
                
                await log_chat(f"Typing {value} into {selector}")
                await session.type_text(selector, value)
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
    async def get_all_links_with_text() -> list:
        """
        Extract all hyperlinks from the page with their text.

        Returns:
            A list of dictionaries with text and href.
        """
        await log_chat("Getting all links with text")
        try:
            return await session.get_all_links_with_text()
        except Exception as e:
            return f"{e}"
        
    @tool
    async def get_all_files():
        """
        Get all files and folders inside the 'files' directory recursively.

        Returns:
            A dictionary containing a list of all nodes (files + folders).
        """

        await log_chat("Getting full file tree (including empty folders)")

        try:
            os.makedirs("files", exist_ok=True)

            nodes = []

            for root, dirs, files in os.walk("files"):
                
                # ✅ Add folders (including empty ones)
                for d in dirs:
                    full_path = os.path.abspath(os.path.join(root, d))
                    project_path = os.path.join(root, d)

                    nodes.append({
                        "name": d,
                        "path": full_path,
                        "project_path": project_path,
                        "type": "folder"
                    })

                # ✅ Add files
                for f in files:
                    full_path = os.path.abspath(os.path.join(root, f))
                    project_path = os.path.join(root, f)

                    nodes.append({
                        "name": f,
                        "path": full_path,
                        "project_path": project_path,
                        "type": "file"
                    })

            result = {
                "nodes": nodes
            }

            await log_chat(str(result))

            return result

        except Exception as e:
            await log_chat(f"Error getting all files: {e}")
            return {"error": str(e)}
        
    @tool
    async def save_to_file(content: str, filename: str) -> str:
        """
        Save content to a file.

        Args:
            content: Content to save.
            filename: Name of the file with extension and directory if applicable

        Returns:
            Confirmation message.
        """
        await log_chat("Saving to file")
        await log_chat(f"Filename: {filename}")
        if not filename.startswith("files/"):
            return f"Invalid filename: {filename}. Please provide a filename inside files/ directory."
        try:
            if not os.path.exists("files"):
                os.makedirs("files")
            with open(f"{filename}", "w") as f:
                f.write(content)
            return f"Saved to file {filename}"
        except Exception as e:
            await log_chat(f"Error saving to file: {e}")
            return f"{e}"

    @tool
    async def delete_file(filepath: str) -> str:
        """
        Delete a file.

        Args:
            filepath: Name of the file to delete with the path.
        
        Returns:
            Confirmation message.
        """
        await log_chat(f"Deleting file: {filepath}")
        if not os.path.exists(filepath):
            return f"File not found: {filepath}"
        if not filepath.startswith("files/"):
            return f"Invalid filepath: {filepath}"
        if os.path.isdir(filepath):
            return f"Invalid filepath: {filepath}. It is a directory. Please provide a file path."
        
        user_confirmation = await get_user_confirmation(f"Are you sure you want to delete {filepath}?")

        if not user_confirmation:
            return f"File not deleted as per user confirmation."
        try:
            if not os.path.exists(filepath):
                return f"File not found: {filepath}"
            os.remove(filepath)
            return f"Deleted {filepath}"
        except Exception as e:
            await log_chat(f"Error deleting file: {e}")
            return f"{e}"

    @tool
    async def create_directory(dirname: str) -> str:
        """
        Create a directory.

        Args:
            dirname: Name of the directory to create.
        
        Returns:
            Confirmation message.
        """
        await log_chat(f"Creating directory: {dirname}")
        if not dirname.startswith("files/"):
            return f"Invalid dirname: {dirname}. Please provide a directory name inside files/ directory."
        if os.path.exists(f"{dirname}"):
            return f"Directory already exists: {dirname}"
        try:

            os.makedirs(f"{dirname}", exist_ok=True)
            return f"Created directory {dirname}"
        except Exception as e:
            await log_chat(f"Error creating directory: {e}")
            return f"{e}"

    @tool
    async def delete_directory(dirname: str) -> str:
        """
        Delete a directory.

        Args:
            dirname: Name of the directory to delete.
        
        Returns:
            Confirmation message.
        """
        await log_chat(f"Deleting directory: {dirname}")
        if not dirname.startswith("files/"):
            return f"Invalid dirname: {dirname}. Please provide a directory name inside files/ directory."
        if not os.path.exists(f"{dirname}"):
            return f"Directory not found: {dirname}"
        try:
            shutil.rmtree(f"{dirname}")
            return f"Deleted directory {dirname}"
        except Exception as e:
            await log_chat(f"Error deleting directory: {e}")
            return f"{e}"

    @tool
    async def move_file(src: str, dst: str) -> str:
        """
        Move a file.

        Args:
            src: Source file path.
            dst: Destination file path.
        
        Returns:
            Confirmation message.
        """
        await log_chat(f"Moving file: {src} → {dst}")
        if not os.path.exists(src):
            return f"File not found: {src}"
        if os.path.exists(dst):
            return f"File already exists at destination: {dst}"
        if not src.startswith("files/"):
            return f"Invalid src: {src}. Please provide a source path inside files/ directory."
        if not dst.startswith("files/"):
            return f"Invalid dst: {dst}. Please provide a destination path inside files/ directory."
        try:
            shutil.move(src, dst)
            return f"Moved {src} → {dst}"
        except Exception as e:
            await log_chat(f"Error moving file: {e}")
            return f"{e}"

    @tool
    async def read_file(filepath: str) -> str:
        """
        Read content from a file.

        Args:
            filepath: Name of the file to read with the path.

        Returns:
            Content of the file.
        """
        await log_chat("Reading file")
        try:
            with open(filepath, "r") as f:
                return f.read()
        except Exception as e:
            return f"{e}"

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
    async def update_memory(content: str) -> str:
        """
        Update the memory with the given content.

        Args:
            content: Content to update the memory with.
        
        Returns:
            Confirmation message.
        
        """
        await log_chat(f"Updating memory with {content}")
        try:
            if os.dir.exists("memory"):
                os.makedirs("memory")
            if os.path.exists("memory/memory.md"):
                with open("memory/memory.md", "a") as f:
                    f.write(content)
            else:
                with open("memory/memory.md", "w") as f:
                    f.write(content)
            return f"Updated memory with sucessfully."
        except Exception as e:
            return f"{e}"

    @tool
    async def read_memory() -> str:
        """
        Read the memory.

        Returns:
            Content of the memory.
        """
        await log_chat(f"Reading memory")
        try:
            if not os.path.exists("memory/memory.md"):
                return "Memory not found"
            with open("memory/memory.md", "r") as f:
                return f.read()
        except Exception as e:
            return f"{e}"


    

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
    ]

    if misc_tools:
        return misc_tools_list
    else:
        return browser_tools + misc_tools_list
