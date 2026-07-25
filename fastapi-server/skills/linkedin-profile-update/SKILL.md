---
name: linkedin-profile-update
description: Update LinkedIn profile sections including headline, summary, experience, education, skills, and other profile details through browser automation.
license: MIT
---

# LinkedIn Profile Update Skill

## When to Use
- User asks to update their LinkedIn profile
- User wants to edit headline, summary, about section, or experience
- User wants to add new skills, education, or certifications
- User wants to optimize their profile for job search or networking

## Prerequisites
- User must be logged into LinkedIn (pause and ask via `get_user_confirmation` if not)
- User should provide the specific changes they want to make

## Profile Sections You Can Update

### 1. Headline
- Navigate to `linkedin.com/in/<profile-id>/edit/intro/`
- Update the headline field
- Save changes

### 2. About/Summary
- Navigate to `linkedin.com/in/<profile-id>/edit/about/`
- Update the summary text
- Save changes

### 3. Experience
- Navigate to `linkedin.com/in/<profile-id>/edit/experience/`
- Add new position or edit existing
- Fields: Title, Company, Location, Date Range, Description

### 4. Education
- Navigate to `linkedin.com/in/<profile-id>/edit/education/`
- Add new education entry or edit existing
- Fields: School, Degree, Field of Study, Dates

### 5. Skills
- Navigate to `linkedin.com/in/<profile-id>/edit/skills/`
- Add new skills or reorder existing
- Request skill endorsements from connections

### 6. Featured Section
- Navigate to `linkedin.com/in/<profile-id>/edit/featured/`
- Add or remove featured content (posts, articles, links, media)

## Workflow

### 1. Understand Changes
Before making edits, confirm with the user via `get_user_confirmation`:
- **Section** — which part of the profile to update
- **Current content** — what's there now (optional, can read from page)
- **Desired changes** — what to add, modify, or remove
- **Tone/style** — professional, casual, keyword-optimized

### 2. Navigate to Profile
1. `open_url` to `linkedin.com/in/<profile-id>/` (or ask user for their profile URL)
2. `get_user_confirmation` to verify user is logged in
3. Take a snapshot of current profile state using `get_page_text`

### 3. Make Edits
For each section to update:
1. Navigate to the edit URL for that section
2. Use `get_ui_schema` to identify form fields
3. Use `type_text` to fill in new content
4. Use `click` to save changes
5. Verify changes were saved by navigating back to profile

### 4. Verify Changes
1. Navigate back to the main profile page
2. Use `get_page_text` to confirm changes are visible
3. Report back to user what was updated

## Edit URLs Reference
- **Intro/Headline:** `/in/<id>/edit/intro/`
- **About:** `/in/<id>/edit/about/`
- **Experience:** `/in/<id>/edit/experience/`
- **Education:** `/in/<id>/edit/education/`
- **Skills:** `/in/<id>/edit/skills/`
- **Featured:** `/in/<id>/edit/featured/`
- **Certifications:** `/in/<id>/edit/certifications/`
- **Languages:** `/in/<id>/edit/languages/`
- **Interests:** `/in/<id>/edit/interests/`

## Tips for Profile Optimization
- **Headline:** Include relevant keywords, not just job title (e.g., "Software Engineer | Python | Machine Learning | Open Source")
- **About:** Start with a strong opening, use short paragraphs, include achievements with metrics
- **Experience:** Use action verbs, quantify results, include relevant keywords
- **Skills:** List top 3 skills first (most visible), align with target job descriptions

## Rules
- Never publish changes without explicit user confirmation via `get_user_confirmation`
- If LinkedIn shows a CAPTCHA or login prompt, pause and ask user to complete manually
- Save all edits before navigating away from edit pages
- If a section cannot be edited (permissions, restrictions), note the issue and move on
- Always show the user a preview of changes before saving when possible
- If the user provides a profile URL, extract the profile ID from it
