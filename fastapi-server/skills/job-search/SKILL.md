---
name: job-search
description: Search for jobs across platforms like LinkedIn, Naukri, Indeed, and company career pages. Extract job details, compare listings, and compile organized reports.
license: MIT
---

# Job Search Skill

## When to Use
- User asks to find jobs, search for openings, or look for roles
- User wants to compare job listings across platforms
- User asks about hiring trends or salary ranges for a role

## Platforms to Search
- **LinkedIn** — `linkedin.com/jobs/search/?keywords=<query>&location=<location>`
- **Naukri** — `naukri.com/<role>-jobs?experience=<exp>&location=<loc>`
- **Indeed** — `indeed.com/jobs?q=<query>&l=<location>`
- **Glassdoor** — `glassdoor.com/Job/<role>-jobs-SRCH_KO0,<len>.htm`
- **Company career pages** — Direct URLs if user specifies companies

## Workflow

### 1. Understand Requirements
Before searching, confirm with the user via `get_user_confirmation`:
- **Role/keywords** — job title, skills, or technology
- **Location** — city, remote, or hybrid preference
- **Experience level** — fresher, mid, senior
- **Salary range** — if specified
- **Company preferences** — specific companies or open to all

### 2. Search Strategy
For each platform:
1. `open_url` to the job search page
2. Enter search criteria using `type_text` and `click`
3. `get_ui_schema` to identify job listing cards
4. For each relevant listing:
   - Click into the listing
   - `get_page_text` or `get_ui_schema` to extract details
   - Record: title, company, location, salary (if listed), experience, posted date, key requirements
   - `update_memory` to store the listing
5. Scroll to load more results and repeat

### 3. Data to Extract Per Listing
- Job title
- Company name
- Location (and remote/hybrid/on-site status)
- Experience required
- Salary/CTC (if available)
- Key skills/requirements
- Posted date
- Application URL or method
- Any notable perks or benefits

### 4. Compile Report
After searching all platforms:
1. `read_memory` to gather all collected listings
2. `write_file` to save a structured report:

```markdown
# Job Search Report

## Search Criteria
- Role: <role>
- Location: <location>
- Experience: <exp>

## Listings

### 1. <Job Title> — <Company>
- **Location:** <location>
- **Experience:** <exp>
- **Salary:** <salary or "Not specified">
- **Key Skills:** <skills>
- **Posted:** <date>
- **Link:** <url>
- **Notes:** <any notable details>

### 2. ...
```

3. Present a summary to the user with the top matches

## Rules
- Never apply to jobs or submit applications without explicit user confirmation
- If a platform requires login, pause and ask the user via `get_user_confirmation`
- Always record the source URL for each listing
- Deduplicate listings that appear on multiple platforms
- If a site blocks access, move to the next platform and note the issue
- Sort results by relevance and recency
