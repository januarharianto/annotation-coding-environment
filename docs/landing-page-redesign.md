# Landing Page Redesign

## Summary

Simplify the landing page. Drop the username prompt, merge New/Open into one row, add a Tools section for Inter-Coder Agreement. Left-aligned, single column, text links only.

## Current problems

- Username prompt on first launch is a barrier — coder name should be asked during project creation instead
- "New Project" and "Open Project" are two separate buttons that feel repetitive
- Inter-Coder Agreement is a standalone link with no section — needs room to grow as more tools are added
- Coder name in localStorage is completely disconnected from the database — all projects currently store coder name as "default"

## Design

Left-aligned, single column. Three labelled sections separated by spacing (no border lines):

```
START
New project | Open file

RECENT
Interview Study.ace                    2h ago
Focus Groups.ace                    Yesterday
Survey Responses.ace                   3 days

TOOLS
Inter-Coder Agreement
```

### Start section
- "New project" and "Open file" on the same line, separated by a pipe `|`
- Both are plain text links (no buttons)
- "New project" flow:
  1. Click "New project" — inline input expands below the Start row (same expand behaviour as current)
  2. Type project name, press Enter
  3. Folder picker opens (with cloud-sync warning preserved if user picks a synced folder)
  4. Coder name input appears inline (pre-filled from localStorage if available)
  5. Press Enter — project is created with the coder name passed to the server
- "Open file" opens the native file picker for `.ace` files

### Recent section
- Label: "RECENT" (uppercase, small, grey)
- Shows up to 5 recent projects, newest first
- Each row: project filename on the left, relative time on the right
- Click opens the project
- Empty state: "No recent projects" in light grey
- Data source: localStorage, format `{path, openedAt}` objects (migration from old string format preserved)

### Tools section
- Label: "TOOLS" (uppercase, small, grey)
- "Inter-Coder Agreement" as a text link
- Extensible — more tools can be added as plain links

### Preserved from current implementation
- Cloud-sync folder warning (`confirm()` dialog when user picks Dropbox/OneDrive/iCloud/Google Drive folder)
- Overwrite confirmation dialog via `#modal-container` + HTMX `afterSwap` auto-open
- `window._aceAddRecent` function (used by other contexts to add to recent list)

### Removed
- Username prompt on first launch — coder name moves to project creation flow
- Centred layout — now left-aligned
- Separate New/Open buttons — merged into one row
- Version badge — removed from landing page

### Coder name

Currently the landing page asks for a name on first launch and stores it in localStorage under `ace-coder-name`. However, this value is never sent to the server — `create_project()` in `connection.py` hardcodes `add_coder(conn, "default")`. The name is purely cosmetic.

Changes:
- Remove the name prompt screen entirely
- Ask for coder name as an inline input during the "New project" flow (step 4 above)
- Send coder name to `/api/project/create` as a form field
- `create_project()` in `connection.py` accepts a `coder_name` parameter instead of hardcoding "default"
- Store the name in localStorage for pre-filling on next project creation
- The overwrite dialog's `hx-vals` must also pass the coder name so it isn't lost on retry
- Existing projects with coder name "default" are not migrated — they keep "default" until the user re-exports or creates a new coder package

### Empty state (first launch)
Same layout, but Recent section shows "No recent projects" in light grey. Start and Tools sections are unchanged. No special first-run screen.

## Files to change

- `src/ace/templates/landing.html` — rewrite template and inline JS
- `src/ace/static/css/ace.css` — update `ace-home-*` classes, remove unused rules
- `src/ace/routes/api.py` — modify `/api/project/create` to accept `coder_name` form field, pass it to `create_project()`, include in overwrite dialog `hx-vals`
- `src/ace/db/connection.py` — modify `create_project()` to accept `coder_name` parameter instead of hardcoding `add_coder(conn, "default")`
- `tests/test_db/test_connection.py` — update assertion from `"default"` to match new coder name
- `tests/test_project.py` — update project creation test to pass coder name
