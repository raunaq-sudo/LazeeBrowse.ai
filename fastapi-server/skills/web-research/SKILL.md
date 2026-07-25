---
name: web-research
description: Conduct thorough web research on any topic. Visit multiple sources, extract verified data, and produce organized reports with citations.
license: MIT
---

# Web Research Skill

## When to Use
- User asks to research a topic, investigate a subject, or gather information
- Task requires visiting multiple websites and synthesizing findings
- User wants a report, summary, or comparison based on web data

## Workflow

### 1. Define Scope
Before browsing, confirm with the user via `get_user_confirmation`:
- **Research question** — what exactly needs to be answered
- **Depth** — quick overview vs deep dive
- **Sources** — any specific sites to include or exclude
- **Output format** — report, summary, comparison table, etc.

### 2. Build Strategy
Plan the research approach:
- Identify 3-5 authoritative sources per sub-topic
- Prioritize: official sites, reputable publications, government数据, academic sources
- Define what data to extract from each source
- Present the plan to the user for approval

### 3. Execute Research
For each source:
1. `open_url` to the site
2. `get_ui_schema` to understand page structure
3. `get_page_text` to read the content
4. `scroll` top → middle → bottom to catch all content
5. If the page has relevant sub-links, follow them (depth-first)
6. `update_memory` to record findings with source URL

For search engines:
1. `open_url` to Google or relevant search engine
2. `type_text` the search query into the search bar
3. `get_ui_schema` to identify result links
4. Visit the top 5-8 relevant results
5. Extract data from each

### 4. Data Quality Rules
- **Never fabricate** — only record what is explicitly stated on the page
- **Cite sources** — every data point must include the source URL
- **Cross-reference** — verify key claims across 2+ sources when possible
- **Date awareness** — note when data was published; prefer recent sources
- **Distinguish facts from opinions** — mark editorial content as such

### 5. Compile Report
1. `read_memory` to gather all findings
2. Organize by theme/topic, not by source
3. `write_file` to save the report:

```markdown
# Research Report: <Topic>

## Summary
<Brief overview of key findings>

## Key Findings

### <Theme 1>
<Finding with citation>

### <Theme 2>
<Finding with citation>

## Sources
1. <URL> — <brief description>
2. <URL> — <brief description>
```

4. Present key findings to the user
5. Offer `convert_md` if user wants PDF/DOCX

## Research Patterns

### Comparison Research
When comparing options (products, services, technologies):
- Create a consistent set of criteria
- Visit each option's page
- Extract data using the same criteria
- `write_file` a comparison table

### News/Current Events
- Start with major news aggregators (Google News, specific news sites)
- Check multiple outlets for the same story
- Note publication dates and any updates
- Record both headline facts and context/background

### Technical Research
- Official documentation first
- Community sources (Stack Overflow, GitHub issues, forums) for practical experience
- Version-specific information — note which version is being discussed

## Rules
- If a site requires login, pause and ask the user
- If a site is blocked or inaccessible, skip it and note the issue
- If data contradicts across sources, present both sides with citations
- Never stop at one source — always cross-reference
- If the research scope is too broad, suggest narrowing it down
