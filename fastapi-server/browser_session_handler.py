import asyncio
from dotenv import load_dotenv
load_dotenv()
import os
from typing import List, Dict
from rich import print
import os
from typing import Dict, Optional

class BrowserSession:
    def __init__(self, context):
        self.context = context
        self.pages: Dict[str, any] = {}
        self.max_timeout = 30000
        self.active_page: Optional[str] = None

        # Auto-detect new tabs
        self.context.on("page", self._on_new_page)

    # ---------------- TAB MANAGEMENT ---------------- #

    async def _on_new_page(self, page):
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1000)
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
        name = f"auto_{len(self.pages)+1}"
        self.pages[name] = page
        self.active_page = name
        await self.switch_tab(name)
        print(f"[NEW TAB] {name} -> {page.url}")

    async def new_page(self, name: str, url: str):
        # Prevent duplicate tabs
        for existing_name, p in self.pages.items():
            if url in p.url:
                return f"[INFO] Reusing tab '{existing_name}'"

        page = await self.context.new_page()
        await page.goto(url, timeout=self.max_timeout)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1000)

        self.pages[name] = page
        self.active_page = name

        return f"[OPENED] {url} -> {name}"


    async def search_url(self, page_name, query: str) -> str:
        page = await self.get_page(page_name)

        # 🔍 Candidate selectors for search bar
        selectors = [
            "input[type='search']",
            "input[placeholder*='search' i]",
            "input[name*='search' i]",
            "input[id*='search' i]",
            "input[class*='search' i]"
        ]

        search_box = None

        # ✅ Try all selectors
        for sel in selectors:
            elements = await page.query_selector_all(sel)

            for el in elements:
                try:
                    if await el.is_visible() and await el.is_enabled():
                        search_box = el
                        break
                except:
                    continue

            if search_box:
                break

        # ❌ No search bar found
        if not search_box:
            return "No search bar detected"

        # ✅ Type query
        await search_box.fill("")
        await search_box.fill(query)

        # Try pressing Enter
        try:
            await search_box.press("Enter")
        except:
            pass

        # Optional: click search button if exists
        try:
            await self.submit_form(page_name=page_name)
        except:
            pass



        # Wait for results
        await page.wait_for_timeout(3000)

        content = await page.content()
        return await self.get_ui_schema(page_name=page_name, mode="visible")

    async def get_page(self, name: Optional[str] = None):
        name = name or self.active_page
        if name not in self.pages and name is not None:
            # Create new page
            print("New page opened. As Name of page was not found.")
            await self.new_page(name=name, url="https://www.duckduckgo.com")
        
        if name is None and self.active_page is None:
            raise Exception("No active page and no page name provided")
        
        if name is None and self.active_page is not None:
            name = self.active_page
        
        await self.switch_tab(name)
        

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

    async def close_tab(self, name: str):
        return await self.close_page(name)

    async def close_page(self, name: str):
        page = await self.get_page(name)
        await page.close()
        del self.pages[name]

        if self.active_page == name:
            self.active_page = next(iter(self.pages), None)

        return f"[CLOSED] {name}"

    async def switch_tab(self, name: str):
        if name not in self.pages:
            raise Exception(f"Tab '{name}' not found")
        self.active_page = name
        await self.pages[name].bring_to_front()
        return f"[SWITCHED] {name}"

    async def find_tab_by_url(self, keyword: str):
        for name, page in self.pages.items():
            if keyword in page.url:
                return name
        return None

    async def handle_popups(self, page):
        # Close modals
        modals = page.locator("[role='dialog'], .modal, dialog")

        count = await modals.count()

        for i in range(count):
            modal = modals.nth(i)

            if await modal.is_visible():
                close_btn = modal.locator("button, [aria-label='close']")
                
                if await close_btn.count() > 0:
                    await close_btn.first.click()
                else:
                    await page.keyboard.press("Escape")

        # Accept cookies
        try:
            btn = page.locator("button:has-text('Accept')")
            if await btn.count() > 0:
                await btn.first.click(timeout=self.max_timeout)
        except:
            pass
    # ---------------- ACTIONS ---------------- #

    async def open_url(self, url: str, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        print("Going to url: ", url)
        await page.goto(url, timeout=self.max_timeout)
        print("Waiting for load state: ", page.url)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1000)
        print("Page loaded.")
        # await self.handle_popups(page)
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

        try:
            # Ensure element is ready
            el = page.locator(selector)
            await el.wait_for(state="attached", timeout=2000)

            # Check current value
            value = await el.input_value()

            # If already empty → skip
            if value == "":
                print("Selector is already empty.")
                return f"[CLEAR] {selector} (already empty)"

            # Focus first (important for React inputs)
            await el.click()

            # Clear using fill
            await el.fill("")
            print("Selector cleared.")
            return f"[CLEAR] {selector}"

        except Exception:
            # 🔁 Fallback: keyboard clear (more reliable)
            try:
                el = page.locator(selector)
                await el.click()

                # Select all + delete
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")

                return f"[CLEAR-FALLBACK] {selector}"

            except Exception as e:
                return f"[CLEAR-FAILED] {selector} | {str(e)}"

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

    async def get_visible_modal_schema(self, page_name: Optional[str] = None):
        """
        Returns structured schema for all visible modals/dialogs/overlays.

        Improvements:
        - Better detection (dialog, modal, overlay, portal)
        - Strong selectors
        - Deduplication
        - Action classification
        - Confidence scoring
        """

        page = await self.get_page(page_name)

        # --- Stability wait ---
        try:
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)
            await page.wait_for_timeout(500)
        except:
            pass

        modal_selectors = [
            "dialog",
            "[role='dialog']",
            "[aria-modal='true']",
            ".modal",
            "[class*='modal']",
            "[class*='popup']",
            "[class*='overlay']"
        ]

        result = []
        seen_modals = set()

        async def process_context(context):
            modals = context.locator(", ".join(modal_selectors))
            modal_count = await modals.count()

            for i in range(modal_count):
                modal = modals.nth(i)

                try:
                    # --- visibility check ---
                    if not await modal.is_visible(timeout=500):
                        continue

                    # --- dedupe ---
                    modal_id = await modal.evaluate("el => el.outerHTML.slice(0, 200)")
                    if modal_id in seen_modals:
                        continue
                    seen_modals.add(modal_id)

                    # --- extract elements ---
                    elements = modal.locator("input, textarea, select, button, a")
                    el_count = await elements.count()

                    modal_elements = []
                    seen_elements = set()

                    for j in range(el_count):
                        el = elements.nth(j)

                        try:
                            if not await el.is_visible(timeout=200):
                                continue

                            tag = await el.evaluate("el => el.tagName.toLowerCase()")

                            # --- selector generation ---
                            selector = await el.evaluate("""
                                el => {
                                    if (el.id) return '#' + el.id;

                                    if (el.getAttribute('data-testid'))
                                        return `[data-testid="${el.getAttribute('data-testid')}"]`;

                                    if (el.name)
                                        return `[name="${el.name}"]`;

                                    if (el.className && typeof el.className === 'string') {
                                        const cls = el.className.split(' ').filter(Boolean).slice(0,2).join('.');
                                        if (cls) return el.tagName.toLowerCase() + '.' + cls;
                                    }

                                    return el.tagName.toLowerCase();
                                }
                            """)

                            # --- dedupe elements ---
                            key = f"{tag}|{selector}"
                            if key in seen_elements:
                                continue
                            seen_elements.add(key)

                            element_data = {
                                "tag": tag,
                                "selector": selector,
                                "visible": True
                            }

                            # --- input fields ---
                            if tag == "input":
                                element_data.update({
                                    "type": await el.get_attribute("type"),
                                    "name": await el.get_attribute("name"),
                                    "placeholder": await el.get_attribute("placeholder")
                                })

                            elif tag in ["textarea", "select"]:
                                element_data["name"] = await el.get_attribute("name")

                            elif tag in ["button", "a"]:
                                text = (await el.inner_text()).strip()
                                element_data["text"] = text

                                # --- action classification ---
                                t = text.lower()
                                if "login" in t or "sign in" in t:
                                    element_data["action"] = "submit_login"
                                elif "search" in t:
                                    element_data["action"] = "search"
                                elif "accept" in t:
                                    element_data["action"] = "accept"
                                elif "submit" in t:
                                    element_data["action"] = "submit"

                            # --- confidence scoring ---
                            confidence = 0
                            if selector.startswith("#"): confidence += 3
                            if "data-testid" in selector: confidence += 3
                            if "[name=" in selector: confidence += 2
                            if tag in ["button", "input"]: confidence += 1

                            element_data["confidence"] = confidence

                            modal_elements.append(element_data)

                        except:
                            continue

                    # --- skip empty modals ---
                    if not modal_elements:
                        continue

                    result.append({
                        "modal_index": len(result),
                        "type": await modal.evaluate("""
                            el => {
                                const tag = el.tagName.toLowerCase();
                                const cls = (el.className || "").toLowerCase();

                                if (tag === "dialog") return "dialog";
                                if (cls.includes("drawer")) return "drawer";
                                if (cls.includes("popup")) return "popup";
                                if (cls.includes("overlay")) return "overlay";
                                return "modal";
                            }
                        """),
                        "has_form": any(e["tag"] in ["input", "textarea", "select"] for e in modal_elements),
                        "elements": modal_elements
                    })

                except:
                    continue

        # --- process main page ---
        await process_context(page)

        # --- process iframes (IMPORTANT) ---
        for frame in page.frames:
            try:
                await process_context(frame)
            except:
                continue

        print(f"Modal schema: {result}")
        return result


    async def get_all_inputs_with_placeholder(self, page_name: Optional[str] = None):
        page = await self.get_page(page_name)
        try:
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)
            await page.wait_for_timeout(500)
        except:
            pass

    

        inputs = page.locator("input, textarea, select")
        count = await inputs.count()

        results = []
        seen = set()

        for i in range(count):
            el = inputs.nth(i)

            try:
                if not await el.is_visible(timeout=200):
                    continue

                tag = await el.evaluate("el => el.tagName.toLowerCase()")

                # --- attributes ---
                input_type = await el.get_attribute("type")
                name = await el.get_attribute("name")
                placeholder = await el.get_attribute("placeholder")
                el_id = await el.get_attribute("id")

                # --- selector generation ---
                selector = await el.evaluate("""
                    el => {
                        if (el.id) return '#' + el.id;

                        if (el.getAttribute('data-testid'))
                            return `[data-testid="${el.getAttribute('data-testid')}"]`;

                        if (el.name)
                            return `[name="${el.name}"]`;

                        if (el.className && typeof el.className === 'string') {
                            const cls = el.className.split(' ').filter(Boolean).slice(0,2).join('.');
                            if (cls) return el.tagName.toLowerCase() + '.' + cls;
                        }

                        return el.tagName.toLowerCase();
                    }
                """)

                # --- LABEL DETECTION ---
                label = None

                # 1. <label for="id">
                if el_id:
                    label = await page.evaluate("""
                        (id) => {
                            const lbl = document.querySelector(`label[for="${id}"]`);
                            return lbl ? lbl.innerText.trim() : null;
                        }
                    """, el_id)

                # 2. Parent label
                if not label:
                    label = await el.evaluate("""
                        el => {
                            const parent = el.closest('label');
                            return parent ? parent.innerText.trim() : null;
                        }
                    """)

                # 3. aria-label
                if not label:
                    label = await el.get_attribute("aria-label")

                # 4. previous sibling text
                if not label:
                    label = await el.evaluate("""
                        el => {
                            let prev = el.previousElementSibling;
                            if (prev) return prev.innerText?.trim() || null;
                            return null;
                        }
                    """)

                # --- CONTEXT (parent text) ---
                context = await el.evaluate("""
                    el => {
                        const parent = el.parentElement;
                        return parent ? parent.innerText.slice(0, 100).trim() : null;
                    }
                """)

                # --- dedupe ---
                key = f"{selector}|{placeholder}|{label}"
                if key in seen:
                    continue
                seen.add(key)

                results.append({
                    "tag": tag,
                    "type": input_type,
                    "name": name,
                    "placeholder": placeholder,
                    "label": label,
                    "context": context,
                    "selector": selector
                })

            except:
                continue

        return results

    async def get_all_links_with_metadata(self, page_name: Optional[str] = None):
        """
        Extract all visible links (<a> tags) with:
        - text (robust extraction: innerText + aria + title + fallback)
        - href (absolute)
        - label
        - context
        - selector
        - confidence
        """

        page = await self.get_page(page_name)

        try:
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)
            await page.wait_for_timeout(500)
        except:
            pass

        links = page.locator("a")
        count = await links.count()

        results = []
        seen = set()

        for i in range(count):
            el = links.nth(i)

            try:
                if not await el.is_visible(timeout=200):
                    continue

                # -------------------------------
                # Robust TEXT extraction
                # -------------------------------
                text = (await el.inner_text()).strip()

                if not text:
                    text = await el.get_attribute("aria-label")

                if not text:
                    text = await el.get_attribute("title")

                if not text:
                    text = await el.get_attribute("alt")

                if not text:
                    text = await el.evaluate("""
                        el => {
                            const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                            let node, text = "";
                            while(node = walker.nextNode()) {
                                text += node.textContent.trim() + " ";
                            }
                            return text.trim();
                        }
                    """)

                # -------------------------------
                # HREF handling
                # -------------------------------
                href = await el.get_attribute("href")

                if not href or href.startswith("javascript:"):
                    continue

                # Convert to absolute URL
                href = await el.evaluate("el => el.href")

                # -------------------------------
                # Label fallback
                # -------------------------------
                label = await el.get_attribute("aria-label")
                if not label:
                    label = await el.get_attribute("title")

                # -------------------------------
                # Selector generation
                # -------------------------------
                selector = await el.evaluate("""
                    el => {
                        if (el.id) return '#' + el.id;

                        if (el.getAttribute('data-testid'))
                            return `[data-testid="${el.getAttribute('data-testid')}"]`;

                        if (el.name)
                            return `[name="${el.name}"]`;

                        if (el.className && typeof el.className === 'string') {
                            const cls = el.className.split(' ').filter(Boolean).slice(0,2).join('.');
                            if (cls) return el.tagName.toLowerCase() + '.' + cls;
                        }

                        return el.tagName.toLowerCase();
                    }
                """)

                # -------------------------------
                # Context (parent text)
                # -------------------------------
                context = await el.evaluate("""
                    el => {
                        const parent = el.parentElement;
                        return parent ? parent.innerText.slice(0, 120).trim() : null;
                    }
                """)

                # -------------------------------
                # Confidence scoring
                # -------------------------------
                confidence = 0
                if selector.startswith("#"): confidence += 3
                if "data-testid" in selector: confidence += 3
                if text: confidence += 1
                if href: confidence += 1

                # -------------------------------
                # Deduplication
                # -------------------------------
                key = f"{text}|{href}"
                if key in seen:
                    continue
                seen.add(key)

                results.append({
                    "text": text or "",
                    "href": href,
                    "label": label,
                    "context": context,
                    "selector": selector,
                    "confidence": confidence
                })

            except:
                continue

        return results

    async def get_all_buttons_with_metadata(self, page_name: Optional[str] = None):
        """
        Extract all visible buttons with:
        - text (robust extraction)
        - type (button, submit, etc.)
        - label (aria/title fallback)
        - context (parent text)
        - selector
        - confidence
        """

        page = await self.get_page(page_name)

        try:
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)
            await page.wait_for_timeout(500)
        except:
            pass

        # Covers real-world buttons
        selector_query = "button, input[type=button], input[type=submit], [role='button']"
        buttons = page.locator(selector_query)

        count = await buttons.count()

        results = []
        seen = set()

        for i in range(count):
            el = buttons.nth(i)

            try:
                if not await el.is_visible(timeout=200):
                    continue

                tag = await el.evaluate("el => el.tagName.toLowerCase()")

                # -------------------------------
                # Robust TEXT extraction
                # -------------------------------
                text = ""

                if tag == "input":
                    text = await el.get_attribute("value") or ""
                else:
                    text = (await el.inner_text()).strip()

                if not text:
                    text = await el.get_attribute("aria-label")

                if not text:
                    text = await el.get_attribute("title")

                if not text:
                    text = await el.evaluate("""
                        el => {
                            const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                            let node, text = "";
                            while(node = walker.nextNode()) {
                                text += node.textContent.trim() + " ";
                            }
                            return text.trim();
                        }
                    """)

                # -------------------------------
                # Type
                # -------------------------------
                btn_type = await el.get_attribute("type") or "button"

                # -------------------------------
                # Label fallback
                # -------------------------------
                label = await el.get_attribute("aria-label")
                if not label:
                    label = await el.get_attribute("title")

                # -------------------------------
                # Selector generation
                # -------------------------------
                selector = await el.evaluate("""
                    el => {
                        if (el.id) return '#' + el.id;

                        if (el.getAttribute('data-testid'))
                            return `[data-testid="${el.getAttribute('data-testid')}"]`;

                        if (el.name)
                            return `[name="${el.name}"]`;

                        if (el.className && typeof el.className === 'string') {
                            const cls = el.className.split(' ').filter(Boolean).slice(0,2).join('.');
                            if (cls) return el.tagName.toLowerCase() + '.' + cls;
                        }

                        return el.tagName.toLowerCase();
                    }
                """)

                # -------------------------------
                # Context
                # -------------------------------
                context = await el.evaluate("""
                    el => {
                        const parent = el.parentElement;
                        return parent ? parent.innerText.slice(0, 120).trim() : null;
                    }
                """)

                # -------------------------------
                # Action classification
                # -------------------------------
                action = None
                t = (text or "").lower()

                if "login" in t or "sign in" in t:
                    action = "submit_login"
                elif "search" in t:
                    action = "search"
                elif "add to cart" in t:
                    action = "add_to_cart"
                elif "submit" in t:
                    action = "submit"
                elif "next" in t:
                    action = "next_step"
                elif "accept" in t:
                    action = "accept"
                elif "close" in t:
                    action = "close"

                # -------------------------------
                # Confidence scoring
                # -------------------------------
                confidence = 0
                if selector.startswith("#"): confidence += 3
                if "data-testid" in selector: confidence += 3
                if text: confidence += 1
                if tag in ["button", "input"]: confidence += 1

                # -------------------------------
                # Deduplication
                # -------------------------------
                key = f"{text}|{selector}"
                if key in seen:
                    continue
                seen.add(key)

                results.append({
                    "tag": tag,
                    "type": btn_type,
                    "text": text or "",
                    "label": label,
                    "context": context,
                    "selector": selector,
                    "action": action,
                    "confidence": confidence
                })

            except:
                continue

        return results



    async def get_ui_schema(self, page_name: Optional[str] = None, mode: str = None):
        page = await self.get_page(page_name)
        if mode is None:
            return "Please mention mode. Allowed modes are 'visible', 'interactive', 'full'"
        try:
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)
        except:
            pass

        ui_schema = await page.evaluate(f"""
    () => {{

        const MODE = "{mode}";

        // -------------------------------
        // Visibility
        // -------------------------------
        function isVisible(el) {{
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();

            const inViewport =
                rect.bottom > 0 &&
                rect.right > 0 &&
                rect.top < window.innerHeight &&
                rect.left < window.innerWidth;

            return (
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                parseFloat(style.opacity || "1") > 0 &&
                rect.width > 0 &&
                rect.height > 0 &&
                inViewport
            );
        }}

        function isInteractiveHidden(el) {{
            const cls = (el.className || "").toLowerCase();
            return (
                cls.includes("modal") ||
                cls.includes("popup") ||
                cls.includes("dropdown") ||
                cls.includes("drawer") ||
                el.getAttribute("aria-hidden") === "false"
            );
        }}

        function isUsable(el) {{
            if (MODE === "full") return true;

            if (MODE === "visible") {{
                return isVisible(el);
            }}

            if (MODE === "interactive") {{
                return isVisible(el) || isInteractiveHidden(el);
            }}

            return false;
        }}

        // -------------------------------
        // Selector
        // -------------------------------
        function getSelector(el) {{
            if (el.id) return "#" + el.id;

            if (el.getAttribute("data-testid"))
                return `[data-testid="${{el.getAttribute("data-testid")}}"]`;

            if (el.name)
                return `[name="${{el.name}}"]`;

            if (el.className && typeof el.className === "string") {{
                const cls = el.className.split(" ").filter(Boolean).slice(0, 2).join(".");
                if (cls) return el.tagName.toLowerCase() + "." + cls;
            }}

            return el.tagName.toLowerCase();
        }}

        // -------------------------------
        // Fingerprint (self-healing)
        // -------------------------------
        function safeEncode(str) {{
                return btoa(unescape(encodeURIComponent(str)));
            }}

            function getFingerprint(el) {{
                const tag = el.tagName.toLowerCase();
                const text = (el.innerText || el.placeholder || "").trim().slice(0, 50);

                const parent = el.parentElement;
                const parentTag = parent ? parent.tagName.toLowerCase() : "";

                const rect = el.getBoundingClientRect();

                return safeEncode(
                    tag + "|" +
                    text + "|" +
                    parentTag + "|" +
                    Math.round(rect.x / 50) + "," + Math.round(rect.y / 50)
                );
            }}

        // -------------------------------
        // Confidence
        // -------------------------------
        function confidence(el) {{
            let score = 0;
            if (el.id) score += 3;
            if (el.name) score += 2;
            if (el.innerText) score += 1;
            if (el.getAttribute("data-testid")) score += 3;
            return score;
        }}

        // -------------------------------
        // Action classification
        // -------------------------------
        function classifyAction(text) {{
            const t = (text || "").toLowerCase();

            if (t.includes("login") || t.includes("sign in")) return "submit_login";
            if (t.includes("search")) return "search";
            if (t.includes("add to cart")) return "add_to_cart";
            if (t.includes("next") || t.includes("continue")) return "next_step";
            if (t.includes("accept")) return "accept";
            if (t.includes("submit")) return "submit";

            return null;
        }}

        // -------------------------------
        // Layout
        // -------------------------------
        function getLayout(el) {{
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);

            return {{
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
                zIndex: parseInt(style.zIndex || "0")
            }};
        }}

        // -------------------------------
        // State
        // -------------------------------
        function getState(el) {{
            return {{
                enabled: !el.disabled,
                clickable:
                    el.tagName === "BUTTON" ||
                    el.tagName === "A" ||
                    el.onclick !== null
            }};
        }}

        // -------------------------------
        // Node classification
        // -------------------------------
        function classifyNode(el) {{
            const tag = el.tagName.toLowerCase();

            if (tag === "form") return "form";
            if (tag === "input") return "input";
            if (tag === "button") return "button";
            if (tag === "a") return "link";
            if (tag === "textarea") return "textarea";
            if (tag === "select") return "select";

            if (["section", "article"].includes(tag)) return "section";
            if (["ul", "ol"].includes(tag)) return "list";
            if (tag === "li") return "list_item";

            return "container";
        }}

        function extractText(el) {{
                if (el.innerText && el.innerText.trim().length < 80) {{
                    return el.innerText;
                }}

                if (el.getAttribute("aria-label")) {{
                    return el.getAttribute("aria-label");
                }}

                if (el.title) {{
                    return el.title;
                }}

                return el.innerText.slice(0, 80);
            }}


        // -------------------------------
        // Extract meta
        // -------------------------------
        function extractMeta(el) {{
            const tag = el.tagName.toLowerCase();
            let text = extractText(el)

            if (tag === "input") {{
                text = el.placeholder || el.value || "";
            }}

            return {{
                tag,
                type: tag === "a" ? "link" : tag,
                text: (text || "").trim(),
                placeholder: el.placeholder || null,
                name: el.name || null,
                id: el.id || null,
                selector: getSelector(el),
                fingerprint: getFingerprint(el),
                confidence: confidence(el),
                action: classifyAction(text),
                state: getState(el),
                layout: getLayout(el)
            }};
        }}

        // -------------------------------
        // Build tree
        // -------------------------------
        function buildTree(root, depth = 0, maxDepth = 5) {{
            if (depth > maxDepth) return null;
            if (!isUsable(root)) return null;

            const nodeType = classifyNode(root);

            const node = {{
                type: nodeType,
                meta: extractMeta(root),
                children: []
            }};

            for (const child of root.children) {{
                const childNode = buildTree(child, depth + 1, maxDepth);
                if (childNode) node.children.push(childNode);
            }}

            // form relationships
            if (nodeType === "form") {{
                node.relationship = {{
                    type: "form",
                    inputs: [],
                    submit: null
                }};

                node.children.forEach(c => {{
                    if (c.type === "input") node.relationship.inputs.push(c.meta);
                    if (c.type === "button") node.relationship.submit = c.meta;
                }});
            }}

            // prune useless containers
            if (
                node.children.length === 0 &&
                !["input", "button", "link", "textarea", "select"].includes(nodeType)
            ) {{
                return null;
            }}

            return node;
        }}

        // -------------------------------
        // Region detection
        // -------------------------------
        function classifyRegion(el) {{
            const tag = el.tagName.toLowerCase();
            const cls = (el.className || "").toLowerCase();

            if (tag === "dialog") return "dialog";
            if (cls.includes("drawer") || cls.includes("sidebar")) return "drawer";
            if (cls.includes("popup")) return "popup";
            if (cls.includes("overlay")) return "overlay";
            if (cls.includes("modal")) return "modal";

            return "region";
        }}

        function isBlocking(el) {{
            const rect = el.getBoundingClientRect();
            return (
                rect.width > window.innerWidth * 0.5 &&
                rect.height > window.innerHeight * 0.5
            );
        }}

        function isOverlayLike(el) {{
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();

            return (
                style.position === "fixed" &&
                parseInt(style.zIndex || "0") > 1000 &&
                rect.width > window.innerWidth * 0.3 &&
                rect.height > window.innerHeight * 0.2
            );
        }}

        const regions = [];
        const seen = new Set();

        const regionSelectors = [
            "dialog",
            "[role='dialog']",
            "[aria-modal='true']",
            ".modal",
            "[class*='modal']",
            "[class*='popup']",
            "[class*='overlay']",
            "[class*='drawer']",
            "[class*='sidebar']"
        ];

        // explicit regions
        regionSelectors.forEach(selector => {{
            document.querySelectorAll(selector).forEach(el => {{
                if (!isUsable(el)) return;
                if (seen.has(el)) return;

                seen.add(el);

                const tree = buildTree(el);
                if (!tree) return;

                regions.push({{
                    id: "region_" + regions.length,
                    type: classifyRegion(el),
                    isBlocking: isBlocking(el),
                    tree
                }});
            }});
        }});

        // overlay heuristics
        document.querySelectorAll("div").forEach(el => {{
            if (seen.has(el)) return;
            if (!isUsable(el)) return;
            if (!isOverlayLike(el)) return;

            seen.add(el);

            const tree = buildTree(el);
            if (!tree) return;

            regions.push({{
                id: "region_" + regions.length,
                type: "overlay",
                isBlocking: true,
                tree
            }});
        }});

        // main page
        const mainTree = buildTree(document.body);

        if (mainTree) {{
            regions.push({{
                id: "main",
                type: "page",
                isBlocking: false,
                tree: mainTree
            }});
        }}

        return {{ regions }};
    }}
    """)
        print(ui_schema)
        print(f"Mode: {mode}")
        return ui_schema
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
