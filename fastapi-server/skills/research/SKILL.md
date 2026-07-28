---
name: research
description: Deep web research using multi-engine search, link consolidation, and thorough source analysis. Handles logins, CAPTCHAs, PDFs, and lazy-loaded content.
license: MIT
---

# Research Skill

## When to Use
- User asks to research a topic, investigate a subject, or gather information from the web
- Task requires visiting multiple websites and synthesizing findings
- User wants a report, summary, or comparison based on web data
- Any task that begins with "research", "find out", "investigate", "look up"

## Phase 1 — Multi-Engine Search

**Never navigate to a URL you invented.** Every URL must come from search results.

Search all three engines sequentially:

1. `open_url("https://duckduckgo.com/?q=QUERY")` → `get_search_results()` → collect `[{title, url, snippet}]`
2. `open_url("https://www.google.com/search?q=QUERY")` → `get_search_results()` → collect results
3. `open_url("https://search.brave.com/search?q=QUERY")` → `get_search_results()` → collect results

If one engine fails (CAPTCHA, block), skip it and note it. Attempt minimum 2 engines.

**Consolidate results:**
1. Merge all URLs into one list
2. Deduplicate by domain+path
3. Score by frequency — URLs appearing in multiple engines rank higher
4. Pick top 3-5 URLs as visit candidates

## Phase 2 — Confirmation

Present the user with:
- How many results each engine returned
- Which URLs appeared in multiple engines (cross-referenced)
- Top 3-5 picks with reasons
- What you plan to extract from each

**Wait for user approval before navigating.**

## Phase 3 — Deep Dive

For each confirmed URL:

### Step 1: Navigate and Load
1. `open_url` to the page
2. If the page shows a **login wall or CAPTCHA**:
   - Ask user via `get_user_confirmation("Login required at [URL]. Please log in and confirm when done.")`
   - If user says **yes**: wait, then re-extract after login
   - If user says **no**: try `get_page_text()` and `get_all_links()` to extract whatever is publicly visible. If that fails, skip the URL entirely and note it.
3. **Always scroll to load all content:**
   - `scroll(800)` → `get_page_text()` to check for new content
   - `scroll(800)` → `get_page_text()` again
   - Repeat until no new content appears or bottom is reached
   - This catches lazy-loaded images, infinite scroll, and dynamically rendered data

### Step 2: Extract Data
- `get_page_text()` for main content
- `get_all_links()` for sub-pages to follow
- `get_all_headings()` for structure
- `get_ui_schema()` to understand interactive elements

### Step 3: PDF Handling
If the page contains PDF links:
1. Use `get_total_tokens("filename.pdf")` to check the file size before reading
2. If estimated tokens > 10,000:
   - Ask user via `get_user_confirmation("Found a large PDF (~X tokens). Download and read it?")`
   - If **yes**: download via `write_file` (if accessible) or extract via `get_page_text`
   - If **no**: skip the PDF, note its URL and size, extract whatever summary/snippet is available on the linking page
3. If estimated tokens ≤ 10,000: download and read directly

### Step 3b: File Reading
Before reading any downloaded file, always call `get_total_tokens("filename")` first:
- If tokens > 10,000: ask user via `get_user_confirmation("File is ~X tokens. Read it?")`
- If ≤ 10,000: read directly

### Step 4: Follow Sub-Links
- For each relevant sub-link found, repeat Steps 1-3 (but don't re-search engines)
- Mark visited URLs to avoid loops
- Maximum 3 levels of depth

## Phase 4 — Compile Report

1. Organize findings by theme/topic, not by source
2. Every data point must include its source URL
3. Cross-reference key claims across 2+ sources
4. Note publication dates; prefer recent data
5. Distinguish facts from opinions
6. Save report via `write_file` in markdown format

## Data Quality Rules

- **Never fabricate** — only record what is explicitly stated on the page
- **Cite sources** — every claim must have a URL
- **Date awareness** — note when data was published
- **Contradictions** — if sources disagree, present both with citations
- **Minimum 3 sources** — never stop at one source

## Rules

- Always ask user to login or fill CAPTCHA when encountered
- If user declines login/CAPTCHA, extract whatever is available by other means (public pages, snippets, search results)
- Always scroll pages to ensure all lazy-loaded content is captured
- Only download PDFs after user approval and only if > 10,000 tokens
- Use `get_search_results` on search engine pages, not `get_page_text`
- Use `action_logger` to report progress to the user at each phase
