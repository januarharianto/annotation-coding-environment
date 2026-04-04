# Landing Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the landing page — drop the username prompt, merge New/Open into one row, add a Tools section, pass coder name through to the database.

**Architecture:** Rewrite `landing.html` template and CSS for the new left-aligned three-section layout (Start, Recent, Tools). Modify the backend to accept a `coder_name` parameter on project creation and store it in the database instead of hardcoding "default".

**Tech Stack:** Jinja2, HTMX, FastAPI, SQLite, vanilla JS

**Spec:** `docs/landing-page-redesign.md`

---

## File Map

### Modified files
- `src/ace/db/connection.py:13-38` — add `coder_name` parameter to `create_project()`
- `src/ace/routes/api.py:162-210` — accept `coder_name` in project create endpoint, include in overwrite dialog
- `src/ace/templates/landing.html` — full rewrite (template + JS)
- `src/ace/static/css/ace.css:218-379` — replace `ace-home-*` CSS rules
- `tests/test_project.py` — update project creation tests to pass coder name

---

## Task 1: Backend — coder name parameter

Add `coder_name` parameter to `create_project()` and the API endpoint.

**Files:**
- Modify: `src/ace/db/connection.py:13-38`
- Modify: `src/ace/routes/api.py:162-210`
- Test: `tests/test_project.py`

- [ ] **Step 1: Write failing test for coder name**

Add to `tests/test_project.py`:

```python
def test_create_project_with_coder_name(client, tmp_path):
    """POST /api/project/create stores the provided coder name."""
    import sqlite3
    path = str(tmp_path / "named.ace")
    resp = client.post(
        "/api/project/create",
        data={"name": "Test", "path": path, "coder_name": "Alice"},
    )
    assert Path(path).exists()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    coder = conn.execute("SELECT name FROM coder LIMIT 1").fetchone()
    conn.close()
    assert coder["name"] == "Alice"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_project.py::test_create_project_with_coder_name -v
```

Expected: FAIL — either `coder_name` is ignored and the coder is named "default", or the form parameter is rejected.

- [ ] **Step 3: Modify `create_project()` in connection.py**

In `src/ace/db/connection.py`, change the function signature and the `add_coder` call:

```python
def create_project(
    path: str | Path, name: str, description: str | None = None,
    coder_name: str = "default",
) -> sqlite3.Connection:
```

And change line 37 from:

```python
    add_coder(conn, "default")
```

to:

```python
    add_coder(conn, coder_name)
```

- [ ] **Step 4: Modify `project_create()` in api.py**

In `src/ace/routes/api.py`, add the `coder_name` form parameter to the endpoint (line 163-167):

```python
@router.post("/project/create")
async def project_create(
    request: Request,
    name: str = Form(...),
    path: str = Form(...),
    overwrite: bool = Form(default=False),
    coder_name: str = Form(default="default"),
):
```

Pass it to `create_project()` (line 200):

```python
        conn = create_project(str(file_path), name, coder_name=coder_name)
```

And include it in the overwrite dialog's `hx-vals` JSON (line 189). Change:

```python
                f'hx-vals=\'{{"name":"{name}","path":"{file_path}","overwrite":"true"}}\' '
```

to:

```python
                f'hx-vals=\'{{"name":"{esc_name}","path":"{file_path}","overwrite":"true","coder_name":"{esc_coder}"}}\' '
```

Where `esc_name` and `esc_coder` are HTML-escaped versions. Add before the dialog HTML:

```python
        import html
        esc_name = html.escape(name, quote=True)
        esc_coder = html.escape(coder_name, quote=True)
```

And use `esc_name` in place of `name` in the existing `hx-vals` too.

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_project.py -v
```

Expected: all tests pass including the new one. The existing tests should still pass because `coder_name` defaults to "default".

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest
```

Expected: all tests pass. No other code calls `create_project()` with a positional `coder_name`, so the default preserves backwards compatibility.

- [ ] **Step 7: Commit**

```bash
git add src/ace/db/connection.py src/ace/routes/api.py tests/test_project.py
git commit -m "feat: accept coder name in project creation"
```

---

## Task 2: Landing page template rewrite

Replace the landing page HTML and JS with the new design.

**Files:**
- Modify: `src/ace/templates/landing.html` — full rewrite

- [ ] **Step 1: Replace landing.html**

Replace the entire content of `src/ace/templates/landing.html` with:

```html
{% extends "base.html" %}

{% block title %}ACE{% endblock %}

{% block content %}
<main class="ace-landing">
  <div class="ace-home">

    <!-- Start -->
    <div class="ace-home-section">
      <p class="ace-home-section-label">Start</p>
      <div class="ace-home-start-row">
        <a id="new-project-link" href="#"
           onclick="toggleNewProject(); return false">New project</a>
        <span class="ace-home-pipe">|</span>
        <a href="#" onclick="openExisting(); return false">Open file</a>
      </div>
    </div>

    <!-- New project expand (hidden by default) -->
    <div id="new-project-wrap" class="ace-home-expand">
      <input id="new-project-input" class="ace-home-input"
             placeholder="Project name..." aria-label="New project name">
      <p class="ace-home-input-hint">press Enter to choose folder</p>
    </div>

    <!-- Coder name expand (hidden by default, shown after folder pick) -->
    <div id="coder-name-wrap" class="ace-home-expand">
      <input id="coder-name-input" class="ace-home-input"
             placeholder="Your name..." aria-label="Coder name">
      <p class="ace-home-input-hint">press Enter to create project</p>
    </div>

    <!-- Recent -->
    <div class="ace-home-section">
      <p class="ace-home-section-label">Recent</p>
      <div id="recent-list"></div>
      <p id="empty-hint" class="ace-home-empty" style="display:none">No recent projects</p>
    </div>

    <!-- Tools -->
    <div class="ace-home-section">
      <p class="ace-home-section-label">Tools</p>
      <a class="ace-home-tool-link" href="/agreement">Inter-Coder Agreement</a>
    </div>

    <div id="modal-container"></div>
  </div>
</main>
{% endblock %}

{% block scripts %}
<script>
(function() {
  "use strict";

  var STORAGE_KEY = "ace-recent-files";
  var CODER_KEY = "ace-coder-name";
  var cloudPatterns = [/dropbox/i, /onedrive/i, /icloud/i, /google\s*drive/i];

  // --- Relative time ---
  function relativeTime(ts) {
    var now = Date.now();
    var diff = now - ts;
    if (diff < 0) diff = 0;
    var sec = Math.floor(diff / 1000);
    if (sec < 60) return "Just now";
    var min = Math.floor(sec / 60);
    if (min < 60) return min + (min === 1 ? " minute ago" : " minutes ago");
    var hr = Math.floor(min / 60);
    if (hr < 24) return hr + (hr === 1 ? " hour ago" : " hours ago");
    var days = Math.floor(hr / 24);
    if (days === 1) return "Yesterday";
    if (days < 7) return days + " days ago";
    var weeks = Math.floor(days / 7);
    return weeks + (weeks === 1 ? " week ago" : " weeks ago");
  }

  // --- New project flow ---
  var newWrap = document.getElementById("new-project-wrap");
  var newInput = document.getElementById("new-project-input");
  var coderWrap = document.getElementById("coder-name-wrap");
  var coderInput = document.getElementById("coder-name-input");
  var pendingProjectName = "";
  var pendingProjectPath = "";

  window.toggleNewProject = function() {
    if (newWrap.classList.contains("open")) {
      newWrap.classList.remove("open");
      coderWrap.classList.remove("open");
      newInput.value = "";
      coderInput.value = "";
      pendingProjectName = "";
      pendingProjectPath = "";
    } else {
      newWrap.classList.add("open");
      setTimeout(function() { newInput.focus(); }, 180);
    }
  };

  newInput.addEventListener("keydown", function(e) {
    if (e.key === "Escape") {
      window.toggleNewProject();
      return;
    }
    if (e.key !== "Enter") return;
    var name = this.value.trim();
    if (!name) return;
    this.disabled = true;
    this.placeholder = "Choosing folder...";

    fetch("/api/native/pick-folder", { method: "POST" })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        newInput.disabled = false;
        newInput.placeholder = "Project name...";
        if (!data.path) return;

        // Cloud sync warning
        var lower = data.path.toLowerCase();
        var isCloud = cloudPatterns.some(function(re) { return re.test(lower); });
        if (isCloud && !confirm(
          "This folder appears to be cloud-synced (Dropbox, OneDrive, iCloud). " +
          "SQLite databases can corrupt when synced.\n\nContinue anyway?"
        )) return;

        pendingProjectName = name;
        pendingProjectPath = data.path.replace(/\/$/, "") + "/" + name.replace(/\.ace$/, "") + ".ace";

        // Show coder name input
        newWrap.classList.remove("open");
        coderWrap.classList.add("open");
        var savedName = localStorage.getItem(CODER_KEY) || "";
        coderInput.value = savedName;
        setTimeout(function() { coderInput.focus(); }, 180);
      });
  });

  coderInput.addEventListener("keydown", function(e) {
    if (e.key === "Escape") {
      window.toggleNewProject();
      return;
    }
    if (e.key !== "Enter") return;
    var coderName = this.value.trim();
    if (!coderName) return;

    localStorage.setItem(CODER_KEY, coderName);
    addRecent(pendingProjectPath);
    coderWrap.classList.remove("open");

    htmx.ajax("POST", "/api/project/create", {
      values: {
        name: pendingProjectName,
        path: pendingProjectPath,
        coder_name: coderName
      },
      target: "#modal-container",
      swap: "innerHTML"
    });
  });

  // --- Open existing ---
  window.openExisting = function() {
    fetch("/api/native/pick-file", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "accept=.ace"
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.path) openProject(data.path);
      });
  };

  function openProject(path) {
    addRecent(path);
    htmx.ajax("POST", "/api/project/open", {
      values: { path: path },
      target: "#modal-container",
      swap: "innerHTML"
    });
  }

  // --- Recent files ---
  function migrateRecent(raw) {
    if (!Array.isArray(raw)) return [];
    return raw.map(function(item) {
      if (typeof item === "string") return { path: item, openedAt: 0 };
      if (item && typeof item.path === "string") return item;
      return null;
    }).filter(Boolean);
  }

  function getRecent() {
    try {
      var raw = JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
      return migrateRecent(raw);
    } catch(e) { return []; }
  }

  function addRecent(path) {
    var list = getRecent().filter(function(item) { return item.path !== path; });
    list.unshift({ path: path, openedAt: Date.now() });
    if (list.length > 5) list = list.slice(0, 5);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    renderRecent();
  }

  function escapeHtml(str) {
    var d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  function renderRecent() {
    var list = getRecent();
    var container = document.getElementById("recent-list");
    var emptyHint = document.getElementById("empty-hint");
    container.innerHTML = "";

    if (!list.length) {
      if (emptyHint) emptyHint.style.display = "block";
      return;
    }

    if (emptyHint) emptyHint.style.display = "none";

    list.forEach(function(item) {
      var parts = item.path.split("/");
      var filename = parts.pop();
      var time = item.openedAt ? relativeTime(item.openedAt) : "";

      var row = document.createElement("a");
      row.href = "#";
      row.className = "ace-home-recent";
      row.onclick = function(e) { e.preventDefault(); openProject(item.path); };

      row.innerHTML =
        '<span class="ace-home-recent-name">' + escapeHtml(filename) + '</span>' +
        '<span class="ace-home-recent-time">' + escapeHtml(time) + '</span>';
      container.appendChild(row);
    });
  }

  window._aceAddRecent = addRecent;

  // Dialog auto-open for overwrite confirmation
  document.addEventListener("htmx:afterSwap", function(evt) {
    if (evt.detail.target.id === "modal-container") {
      var dialog = evt.detail.target.querySelector("dialog");
      if (dialog && !dialog.open) dialog.showModal();
    }
  });

  // --- Init ---
  renderRecent();
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Start the dev server and verify**

```bash
uv run uvicorn ace.app:create_app --factory --host 127.0.0.1 --port 8080 --reload --reload-dir src/ace
```

Open `http://127.0.0.1:8080` and verify:
- No username prompt on first visit
- "New project | Open file" appears under START
- Recent section shows (or "No recent projects")
- Tools section shows "Inter-Coder Agreement"
- Clicking "New project" expands project name input
- After entering name + picking folder, coder name input appears
- Clicking "Open file" opens file picker
- Clicking a recent project opens it
- Agreement link works

- [ ] **Step 3: Commit**

```bash
git add src/ace/templates/landing.html
git commit -m "feat: rewrite landing page — drop username, merge new/open, add tools"
```

---

## Task 3: CSS rewrite

Replace the `ace-home-*` CSS rules for the new layout.

**Files:**
- Modify: `src/ace/static/css/ace.css:218-379`

- [ ] **Step 1: Replace CSS rules**

In `src/ace/static/css/ace.css`, replace lines 218-379 (everything from `.ace-home {` through `.ace-home-hint {`) with:

```css
.ace-home {
  text-align: left;
  max-width: 380px;
  width: 100%;
}
.ace-home-section {
  margin-bottom: var(--ace-space-6);
}
.ace-home-section-label {
  font-size: var(--ace-font-size-2xs);
  font-weight: var(--ace-weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--ace-text-muted);
  margin: 0 0 var(--ace-space-2);
}
.ace-home-start-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--ace-font-size-base);
}
.ace-home-start-row a {
  color: var(--ace-text-muted);
  text-decoration: none;
  cursor: pointer;
  transition: color var(--ace-transition);
}
.ace-home-start-row a:hover {
  color: var(--ace-text);
}
.ace-home-pipe {
  color: var(--ace-border-light);
  user-select: none;
}
.ace-home-expand {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.2s ease;
}
.ace-home-expand.open {
  max-height: 80px;
}
.ace-home-input {
  display: block;
  width: 100%;
  border: none;
  border-bottom: 1px solid var(--ace-border);
  padding: var(--ace-space-2) 0;
  font-size: var(--ace-font-size-base);
  background: transparent;
  color: var(--ace-text);
  outline: none;
}
.ace-home-input:focus {
  border-bottom-color: var(--ace-text);
}
.ace-home-input::placeholder {
  color: var(--ace-border);
}
.ace-home-input-hint {
  font-size: var(--ace-font-size-2xs);
  color: var(--ace-border);
  margin-top: var(--ace-space-1);
}
.ace-home-recent {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px var(--ace-space-2);
  text-decoration: none;
  cursor: pointer;
  transition: background var(--ace-transition);
}
.ace-home-recent:hover {
  background: var(--ace-bg-muted);
}
.ace-home-recent:hover .ace-home-recent-name {
  color: var(--ace-text);
}
.ace-home-recent-name {
  font-size: var(--ace-font-size-md);
  color: var(--ace-text-muted);
  transition: color var(--ace-transition);
}
.ace-home-recent-time {
  font-size: var(--ace-font-size-xs);
  color: var(--ace-border);
}
.ace-home-empty {
  font-size: var(--ace-font-size-md);
  color: var(--ace-border);
  padding: 5px var(--ace-space-2);
}
.ace-home-tool-link {
  display: block;
  padding: 5px var(--ace-space-2);
  font-size: var(--ace-font-size-md);
  color: var(--ace-text-muted);
  text-decoration: none;
  cursor: pointer;
  transition: background var(--ace-transition), color var(--ace-transition);
}
.ace-home-tool-link:hover {
  background: var(--ace-bg-muted);
  color: var(--ace-text);
}
```

- [ ] **Step 2: Verify in browser**

Reload `http://127.0.0.1:8080` and check:
- Layout is left-aligned
- Sections have spacing between them, no border lines
- "New project | Open file" is on one line with pipe
- Recent items show filename left, time right
- Tool link has hover state
- Inline inputs expand/collapse smoothly

- [ ] **Step 3: Commit**

```bash
git add src/ace/static/css/ace.css
git commit -m "style: replace landing page CSS for new left-aligned layout"
```

---

## Task 4: Remove version from landing page route

Clean up the pages.py route since the version badge is removed.

**Files:**
- Modify: `src/ace/routes/pages.py`

- [ ] **Step 1: Check current route**

Read `src/ace/routes/pages.py` to see how the landing page route passes `version`. If it is the only consumer of `__version__`, remove the import. If other routes use it, just stop passing it to the landing template.

- [ ] **Step 2: Remove version from template context**

In the `GET /` route, remove `version` from the template context dictionary. Keep the import if other routes use it.

- [ ] **Step 3: Run tests**

```bash
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/ace/routes/pages.py
git commit -m "refactor: remove version badge from landing page"
```

---

## Task 5: Visual verification

Test the complete flow end-to-end.

- [ ] **Step 1: Test new project flow**

1. Open `http://127.0.0.1:8080`
2. Click "New project"
3. Type a project name, press Enter
4. Pick a folder
5. Coder name input appears (pre-filled if you've created a project before)
6. Type a name, press Enter
7. Project is created, redirects to import page

- [ ] **Step 2: Test open file flow**

1. Click "Open file"
2. Pick an existing `.ace` file
3. Project opens

- [ ] **Step 3: Test recent list**

1. Create or open a project
2. Navigate back to `/`
3. Verify the project appears in Recent with relative time
4. Click it to re-open

- [ ] **Step 4: Test empty state**

1. Clear localStorage (`localStorage.clear()` in browser console)
2. Reload the page
3. Verify "No recent projects" appears under Recent
4. Verify no username prompt appears

- [ ] **Step 5: Test overwrite dialog**

1. Create a project with a name that already exists
2. Verify the overwrite confirmation dialog appears
3. Click Overwrite — verify it works and the coder name is preserved

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 7: Commit any fixes**

```bash
git add -u
git commit -m "fix: address visual testing findings"
```
