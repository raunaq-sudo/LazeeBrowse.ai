import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Input, LoadingIndicator
from textual.containers import VerticalScroll
from textual.reactive import reactive
from playwright.async_api import async_playwright
from textual import events

from deepagents import create_deep_agent


from browser_tool import BrowserSession, build_tools
from langchain.agents import create_agent

from pydantic import BaseModel, Field
from typing import Optional

from config import llm, llm_sys_prmpt_gen

from rich.markup import escape
import pyperclip
# -------------------------------
# ✅ STRICT ROUTER SCHEMA
# -------------------------------
class QueryRouterResponse(BaseModel):
    browsing_required: bool
    response: Optional[str] = Field(None, description="Response")


# -------------------------------
# ✅ CHAT UI COMPONENT
# -------------------------------
from textual.widgets import Static

class ChatMessage(Static):

    selected = reactive(False)

    def __init__(self, text: str, markup=True):
        super().__init__(text, markup=markup)
        self.raw_text = text
        
    def watch_selected(self, value: bool):
        if value:
            self.add_class("selected")
        else:
            self.remove_class("selected")

    async def on_click(self):
        self.selected = not self.selected

    async def on_key(self, event: events.Key):
        if event.key == "space":
            self.selected = not self.selected

# -------------------------------
# ✅ MAIN APP
# -------------------------------
class ChatApp(App):

    CSS = """
    Screen {
        layout: vertical;
    }

    #chat {
        height: 1fr;
        border: round $accent;
        padding: 1;
    }

    Input {
        margin-top: 1;
    }
    """
    BINDINGS = [
        ("c", "copy_selected", "Copy selected"),
        ("a", "select_all", "Select all"),
        ("escape", "clear_selection", "Clear selection"),
    ]

    loading = reactive(False)

    def __init__(self, llm, llm_sys_prmpt_gen, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.chat_history = []
        self.user_input_future = None

        # Router (STRICT STRUCTURED)
        self.router_agent = llm_sys_prmpt_gen.with_structured_output(QueryRouterResponse)

        # Browser agent model
        self.llm = llm

        # Conversational agent
        self.conversational_agent = llm_sys_prmpt_gen

        # Browser execution flag
        # self.browser_execution = False
    # -------------------------------
    # UI
    # -------------------------------
    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(id="user_input", placeholder="Type a message and press Enter...")
        yield LoadingIndicator(id="loader")
        yield VerticalScroll(id="chat")

    def get_messages(self):
        chat = self.query_one("#chat")
        return [w for w in chat.children if isinstance(w, ChatMessage)]


    def watch_loading(self, loading: bool):
        loader = self.query_one("#loader")
        loader.display = loading

    async def user_chat(self, message: str):
        chat = self.query_one("#chat")
        from rich.markup import escape

        safe_message = escape(message)
        await chat.mount(ChatMessage(f"[bold green]You:[/bold green] {safe_message}"))
        chat.scroll_end()

    async def bot_chat(self, message: str):
        chat = self.query_one("#chat")

        safe_message = escape(message)
        await chat.mount(ChatMessage(f"[bold cyan]Bot:[/bold cyan] {safe_message}"))
        chat.scroll_end()

    # -------------------------------
    # COPY + SELECTION ACTIONS
    # -------------------------------
    def action_copy_selected(self):
        selected = [
            w.raw_text
            for w in self.get_messages()
            if w.selected
        ]

        if not selected:
            self.notify("No messages selected")
            return

        text = "\n\n".join(selected)

        try:
            pyperclip.copy(text)
            self.notify("Copied selected messages")
        except:
            self.notify("Copy failed")

    def action_select_all(self):
        for msg in self.get_messages():
            msg.selected = True

    def action_clear_selection(self):
        for msg in self.get_messages():
            msg.selected = False

   
    # -------------------------------
    # VALIDATION
    # -------------------------------
    def validate_router_output(self, r: QueryRouterResponse):
        return r
    # -------------------------------
    # INPUT HANDLER
    # -------------------------------
    async def on_input_submitted(self, event: Input.Submitted):
        user_text = event.value
        event.input.value = ""

        await self.user_chat(user_text)
        if self.user_input_future and not self.user_input_future.done():
            self.user_input_future.set_result(user_text)
            return

        
        self.chat_history.append({"role": "user", "content": user_text})

        self.run_worker(self.generate_response())

    # -------------------------------
    # CORE LOGIC
    # -------------------------------
    async def generate_response(self):

        # -------------------------------
        # LOAD ROUTER PROMPT
        # -------------------------------
        # with open("router_prompt.md") as f:
        #     router_prompt = f.read()

        # last_user_msg = self.chat_history[-1]
        # await self.log_chat(f"Last user message: {last_user_msg}")
        # # -------------------------------
        # # ✅ ROUTER (ALWAYS RUN FIRST)
        # # -------------------------------
        # router_output = None
        # for _ in range(3):
        #     try:
        #         await self.log_chat("Running router...")
        #         router_agent = create_agent(
        #             model=self.llm,
        #             system_prompt=router_prompt,
        #             response_format=QueryRouterResponse
        #         )
        #         router_output = await router_agent.ainvoke({
        #             "messages": self.chat_history
        #         })
        #         break
        #     except Exception as e:
        #         await self.log_chat(str(e))
        #         continue
        # else:
        #     await self.log_chat("Routing failed.")
        #     return
        # router_output = self.clean_up_response(router_output)
        # await self.log_chat(f"Router output: {router_output}")

        # -------------------------------
        # ✅ NO BROWSING → CONVERSATIONAL AGENT (IF NO BROWSING REQUIRED)
        # -------------------------------
        # if not router_output.browsing_required:
        # await self.log_chat(f"No browsing required. Running conversational agent...")
        with open("conversational_agent_system_prompt.md") as f:
            conversational_agent_prompt = f.read()
        convo_agent = create_agent(
            model=self.llm,
            tools=build_tools(session=None, request_user_input=self.request_user_input, log_chat=self.log_chat, misc_tools=True),
            system_prompt=conversational_agent_prompt,
            response_format=QueryRouterResponse
        )
        response = await convo_agent.ainvoke({
            "messages": self.chat_history
        })
        await self.log_chat(f"Conversational agent response: {self.clean_up_response(response)}")
        self.chat_history.append(
            {"role": "assistant", "content": self.clean_up_response(response).response}
        )
        await self.bot_chat(self.clean_up_response(response).response)
        if not self.clean_up_response(response).browsing_required:
            return

        # -------------------------------
        # ✅ BROWSING FLOW
        # -------------------------------
        await self.log_chat("Browsing required. Running browser...")
        user_query = self.chat_history[-1]["content"]

        # -------------------------------
        # SYSTEM PROMPT (ONLY ON FIRST RUN)
        # -------------------------------
    
        await self.log_chat("Generating system prompt...")
        with open("system_prompt_generator.md") as f:
            sys_prompt_gen = f.read()
            
        system_prompt_agent = create_agent(
                model=self.llm,
                system_prompt=sys_prompt_gen
            )
        response_sys_prompt = await system_prompt_agent.ainvoke({
            "messages": self.chat_history
        }
        
        )
        self.system_prompt_cached = self.clean_up_response(response_sys_prompt)
        await self.log_chat(f"System prompt generated...")
        with open("system_prompt.md", "w") as f:
            f.write(self.system_prompt_cached)
            await self.log_chat("System prompt written to file.")

        system_prompt = self.system_prompt_cached
        

        # -------------------------------
        # ✅ BROWSER EXECUTION
        # -------------------------------
        async with async_playwright() as p:
            # self.browser_execution = True
            await self.log_chat("Launching browser...")
            browser = await p.chromium.launch(headless=False, args=[
                    "--disable-notifications",
                    "--disable-geolocation",
                    "--disable-infobars",
                ], downloads_path="files/downloads")
            await self.log_chat("Browser launched. Opening page...")
            context = await browser.new_context(permissions=[])

            page = await context.new_page()

            # Disable JS dialogs
            page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))

            # Block popup tabs
            context.on("page", lambda p: asyncio.create_task(p.close()))

            await self.log_chat("Page opened. Creating session...")
            session = BrowserSession(page)
            await self.log_chat("Session created. Creating tools...")
            tools = build_tools(
                session=session,
                request_user_input=self.request_user_input,
                log_chat=self.log_chat
            )
            await self.log_chat("Tools created. Creating agent...")
            agent = create_deep_agent(
                model=self.llm,
                tools=tools,
                system_prompt=system_prompt,
            )
            await self.log_chat("Agent created. Running agent...")
            try:
                response = await agent.ainvoke(
                    {
                        "messages": [
                            {"role": "user", "content": user_query}
                        ] + self.chat_history
                    },
                    config={"recursion_limit": 500}
                )
            except Exception as e:
                await self.log_chat(str(e))
                await self.log_chat("Retrying agent...")
                try:
                    response = await agent.ainvoke(
                        {
                            "messages": [
                                {"role": "user", "content": user_query}
                            ] + self.chat_history + 
                            [{"role": "system", "content": f"""
                                You are running agian. Please continue from where you left last time. 
                                The last error was : {e}
                                """}]
                        },
                        config={"recursion_limit": 500}
                    )
                except Exception as e:
                    await self.log_chat(str(e))
                    response = f"Agent failed. Error: {e}"
            finally:
                await self.log_chat("Agent execution complete.")
            await browser.close()

        final_response = self.clean_up_response(response)
        await self.log_chat(f"Final response: {final_response[:10]}...")

        self.chat_history.append(
            {"role": "assistant", "content": final_response}
        )

        await self.bot_chat(final_response)
        # self.browser_execution = False


    async def request_user_input(self, prompt: str):
        chat = self.query_one("#chat")

        await chat.mount(ChatMessage(f"[yellow]{prompt}[/yellow]"))
        chat.scroll_end()

        self.user_input_future = asyncio.Future()
        return await self.user_input_future
    # -------------------------------
    # RESPONSE CLEANER
    # -------------------------------
    def clean_up_response(self, response):

        def extract_text(content):
            # Case 1: plain string
            if isinstance(content, str):
                return content

            # Case 2: list of content blocks
            if isinstance(content, list):
                for item in reversed(content):
                    if isinstance(item, dict) and "text" in item:
                        return item["text"]
                    if "structured_response" in content and content.get("structured_response") is not None:
                        return content["structured_response"]

                return str(content)

            # Case 3: dict with text
            if isinstance(content, dict):
                if "text" in content:
                    return content["text"]

                if "structured_response" in content and content.get("structured_response") is not None:
                    return content["structured_response"]

                return str(content)

            return None

        # -------------------------------
        # Case 1: LangChain agent structured response
        # -------------------------------
        if isinstance(response, dict) and "structured_response" in response:
            return response["structured_response"]


        # -------------------------------
        # Case 1: LangChain agent response
        # -------------------------------

        if isinstance(response, dict) and "messages" in response:
            for msg in reversed(response["messages"]):
                content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
                text = extract_text(content)
                if text:
                    return text

        # -------------------------------
        # Case 2: direct dict response
        # -------------------------------
        if isinstance(response, dict):
            content = response.get("content")
            text = extract_text(content)
            if text:
                return text

        # -------------------------------
        # Case 3: AIMessage or similar
        # -------------------------------
        if hasattr(response, "content"):
            text = extract_text(response.content)
            if text:
                return text

        # -------------------------------
        # FINAL FALLBACK (SAFE)
        # -------------------------------
        return f"No readable response generated. {str(response).replace('`', '')}"

    async def log_chat(self, message: str):
        chat = self.query_one("#chat")
        safe_message = escape(message)
        await chat.mount(ChatMessage(f"[gray]Log:{safe_message}[/gray]"))
        chat.scroll_end()

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    ChatApp(llm, llm_sys_prmpt_gen).run()