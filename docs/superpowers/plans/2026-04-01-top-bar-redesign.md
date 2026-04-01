# Top Bar Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the coding page header with a minimal bar: ACE wordmark (home), centred source name + position + clickable flag, and a ? help button.

**Architecture:** Template rebuild of `{% block coding_header %}`, targeted CSS replacement (keeping nav rules intact), and JS changes for event delegation (OOB-swap-safe), Tab zone cycling, and flag toast. No API or data model changes except adding a toast header to the flag response.

**Tech Stack:** Jinja2 templates, vanilla CSS, vanilla JS (bridge.js), existing HTMX flag endpoint

**Spec:** `docs/superpowers/specs/2026-04-01-top-bar-redesign.md`

---

### Task 1: Rebuild Header Template

**Files:**
- Modify: `src/ace/templates/coding.html:56-68`
- Test: `tests/test_coding_routes.py`

- [ ] **Step 1: Write failing test — header has new elements**

Add to `tests/test_coding_routes.py`:

```python
def test_header_has_ace_wordmark_and_source_name(client_with_sources):
    """Header shows ACE wordmark, source display ID, and position counter."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    html = resp.text
    # ACE wordmark as home link
    assert '<a href="/"' in html
    assert "ACE" in html
    # Source display ID (first source is "S001")
    assert "S001" in html
    # Position counter
    assert "1 / 3" in html
    # Semantic header element
    assert "<header" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_coding_routes.py::test_header_has_ace_wordmark_and_source_name -v`
Expected: FAIL — current header has "← Home" and project name, not ACE wordmark or source name.

- [ ] **Step 3: Replace header template**

Replace `{% block coding_header %}` in `src/ace/templates/coding.html` (lines 56-68) with:

```html
  {% block coding_header %}
  <header id="coding-header" class="ace-coding-header">
    <a href="/" class="ace-header-brand">ACE</a>
    <div class="ace-header-centre">
      <span class="ace-header-source" title="{{ current_source.display_id if current_source else '' }}">{{ current_source.display_id if current_source else '' }}</span>
      <span class="ace-header-position" aria-label="Source {{ current_index + 1 }} of {{ total_sources }}">{{ current_index + 1 }} / {{ total_sources }}</span>
      <button type="button" class="ace-flag-btn{% if current_status == 'flagged' %} ace-flag-btn--active{% endif %}"
              aria-label="Toggle flag" aria-pressed="{{ 'true' if current_status == 'flagged' else 'false' }}"
              id="header-flag-btn">
        {%- if current_status == 'flagged' -%}
          <span class="ace-flag-chip">&#9873; Flagged</span>
        {%- else -%}
          <span class="ace-flag-icon">&#9873;</span>
        {%- endif -%}
      </button>
    </div>
    <button type="button" class="ace-header-help" aria-label="Keyboard shortcuts" id="header-help-btn">?</button>
  </header>
  {% endblock %}
```

- [ ] **Step 4: Verify `test_coding_page_shows_project_name` still passes**

The project name was removed from the header but still appears in `<title>` (`{% block title %}Code -- {{ project_name }} -- ACE{% endblock %}`). The existing test at line 138 asserts `"Test Project" in resp.text` — this still passes because `<title>` is in the response. No test changes needed.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/ace/templates/coding.html tests/test_coding_routes.py
git commit -m "feat: rebuild header — ACE wordmark, source name, position counter, flag toggle"
```

---

### Task 2: Header CSS

**Files:**
- Modify: `src/ace/static/css/coding.css`

CRITICAL: The old header CSS (lines 17-128) contains TWO sections interleaved:
1. **Header-specific rules** (lines 17-51, 101-128): `.ace-coding-header`, `.ace-coding-header-back`, `.ace-coding-header-left`, `.ace-coding-header-title`, `.ace-coding-header-right`, `.ace-completion`
2. **Text panel nav rules** (lines 52-100): `.ace-nav-cluster`, `.ace-nav-btn`, `.ace-nav-counter`, `.ace-text-nav` — MUST BE KEPT

- [ ] **Step 1: Replace header-only CSS (lines 17-51)**

Replace lines 17-51 (from `/* ---- Header with merged nav ---- */` through `.ace-coding-header-title`) with:

```css
/* ---- Header ---- */

.ace-coding-header {
  display: flex;
  align-items: center;
  padding: var(--ace-space-2) var(--ace-space-4);
  border-bottom: 1px solid var(--ace-border);
  background: var(--ace-bg);
  height: 40px;
  flex-shrink: 0;
}

.ace-header-brand {
  flex: 0 0 auto;
  font-weight: 700;
  font-size: var(--ace-font-size-sm);
  letter-spacing: -0.3px;
  color: var(--ace-text-muted);
  text-decoration: none;
  transition: color var(--ace-transition);
}

.ace-header-brand:hover { color: var(--ace-text); }

.ace-header-brand:focus-visible {
  outline: 2px solid var(--ace-focus);
  outline-offset: 2px;
  border-radius: var(--ace-radius);
}

.ace-header-centre {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--ace-space-2);
}

.ace-header-source {
  font-weight: var(--ace-weight-semibold);
  font-size: var(--ace-font-size-base);
  color: var(--ace-text);
  max-width: 30ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ace-header-position {
  font-family: var(--ace-font-mono);
  font-size: var(--ace-font-size-xs);
  color: var(--ace-text-muted);
}
```

- [ ] **Step 2: Replace right-side header CSS (lines 101-128)**

Delete lines 101-128 (`.ace-coding-header-right` through `.ace-completion`). Replace with:

```css
/* Flag button */
.ace-flag-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  transition: color var(--ace-transition);
}

.ace-flag-btn:focus-visible {
  outline: 2px solid var(--ace-focus);
  outline-offset: 2px;
  border-radius: var(--ace-radius);
}

.ace-flag-icon {
  color: var(--ace-text-muted);
  font-size: var(--ace-font-size-sm);
}

.ace-flag-btn:hover .ace-flag-icon { color: var(--ace-text); }

.ace-flag-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: rgba(191, 54, 12, 0.1);
  color: #bf360c;
  border: 1px solid rgba(191, 54, 12, 0.25);
  border-radius: var(--ace-radius);
  font-size: var(--ace-font-size-2xs);
  font-weight: 600;
  padding: 1px 6px;
}

.ace-flag-btn:hover .ace-flag-chip { background: rgba(191, 54, 12, 0.16); }

/* Help button */
.ace-header-help {
  flex: 0 0 auto;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--ace-text-muted);
  font-size: var(--ace-font-size-sm);
  padding: var(--ace-space-1);
  transition: color var(--ace-transition);
}

.ace-header-help:hover { color: var(--ace-text); }

.ace-header-help:focus-visible {
  outline: 2px solid var(--ace-focus);
  outline-offset: 2px;
  border-radius: var(--ace-radius);
}
```

DO NOT touch lines 52-100 (`.ace-nav-cluster` through `.ace-text-nav .ace-nav-cluster`) — those are for text panel navigation.

- [ ] **Step 3: Verify in browser**

Open http://127.0.0.1:8080/code and confirm:
- ACE wordmark on the left, muted colour, hover turns dark
- Source name centred, bold, largest text
- Position counter in monospace, muted
- Flag icon (greyed ⚑) visible, hover turns dark
- ? button on the right, muted, hover turns dark
- Text panel navigation (prev/next arrows + counter) still works

- [ ] **Step 4: Commit**

```bash
git add src/ace/static/css/coding.css
git commit -m "style: header CSS — brand, source centre, flag chip, help button"
```

---

### Task 3: Header JavaScript — Event Delegation, Tab Zone, Flag Toast

**Files:**
- Modify: `src/ace/static/js/bridge.js`
- Modify: `src/ace/routes/api.py`

CRITICAL: Header elements are replaced by OOB swaps on every server interaction. Click listeners bound to specific elements in DOMContentLoaded will be destroyed. Use **event delegation** on `document` instead.

- [ ] **Step 1: Add delegated click handlers for header buttons**

Add in bridge.js, near the existing event delegation handlers (e.g. near the group header click handler in section 3, or in section 17). These use event delegation so they survive OOB swaps:

```javascript
  // Header: ? help button (delegated — survives OOB swaps)
  document.addEventListener("click", function (e) {
    if (e.target.closest("#header-help-btn")) {
      _toggleCheatSheet();
    }
  });

  // Header: flag toggle button (delegated — survives OOB swaps)
  document.addEventListener("click", function (e) {
    if (e.target.closest("#header-flag-btn")) {
      _updateCurrentIndex();
      var triggerFlag = document.getElementById("trigger-flag");
      if (triggerFlag) htmx.trigger(triggerFlag, "click");
    }
  });
```

- [ ] **Step 2: Add header to the Tab zone cycle**

Update `_activeZone()` (line 1659) to detect the header. Add the check BEFORE the search bar check (since the header is higher in the DOM):

```javascript
  function _activeZone() {
    var el = document.activeElement;
    if (!el) return null;
    if (el.id === "text-panel" || el.closest("#text-panel")) return "text";
    var header = document.getElementById("coding-header");
    if (header && header.contains(el)) return "header";
    if (el.id === "code-search-input") return "search";
    var tree = document.getElementById("code-tree");
    if (tree && tree.contains(el)) return "tree";
    return null;
  }
```

Update the Tab cycling handler (line 1669). New cycle: text → header → search → tree → text:

```javascript
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Tab") return;

    var zone = _activeZone();
    if (!zone) return;

    if (!e.shiftKey) {
      if (zone === "text") { e.preventDefault(); _focusHeader(); return; }
      if (zone === "header") { e.preventDefault(); _focusSearchBar(); return; }
      if (zone === "search") { e.preventDefault(); _focusCodeTree(); return; }
      if (zone === "tree") { e.preventDefault(); _focusTextPanel(); return; }
    } else {
      if (zone === "text") { e.preventDefault(); _focusCodeTree(); return; }
      if (zone === "header") { e.preventDefault(); _focusTextPanel(); return; }
      if (zone === "search") { e.preventDefault(); _focusHeader(); return; }
      if (zone === "tree") { e.preventDefault(); _focusSearchBar(); return; }
    }
  }, true);
```

Add the `_focusHeader` helper in section 17:

```javascript
  function _focusHeader() {
    var header = document.getElementById("coding-header");
    if (!header) return;
    var first = header.querySelector("a, button");
    if (first) first.focus();
  }
```

- [ ] **Step 3: Guard main keydown handler for header zone**

Find the main keydown handler guard (around line 261) that blocks search and tree zones:

```javascript
    var zone = _activeZone();
    if (zone === "search" || zone === "tree") return;
```

Add `"header"`:

```javascript
    var zone = _activeZone();
    if (zone === "search" || zone === "tree" || zone === "header") return;
```

This prevents letter keys (a-z, q, z, x, etc.) from triggering code application shortcuts while a header button is focused.

- [ ] **Step 4: Add flag announce in afterSettle**

In the `htmx:afterSettle` handler, add a block for header focus restoration and flag announcement. The header is an OOB target, so `afterSettle` fires with `target.id === "coding-header"`:

```javascript
    // Header OOB swap: restore focus if it was in the header
    if (target.id === "coding-header") {
      if (_sidebarFocusState.zone === "header") {
        var flagBtn = document.getElementById("header-flag-btn");
        if (flagBtn) flagBtn.focus();
        _sidebarFocusState.zone = null;
      }
    }
```

Also update the `htmx:beforeSwap` handler to save header focus state. In the existing beforeSwap handler, after the `if (zone === "tree")` block, add:

```javascript
    if (zone === "header") {
      _sidebarFocusState.zone = "header";
    }
```

- [ ] **Step 5: Add toast to flag_route response using X-ACE-Toast header**

Modify `src/ace/routes/api.py` flag_route (line 804). Replace the return at line 829-830:

```python
        content = _render_full_coding_oob(request, conn, coder_id, source_index)
        return HTMLResponse(content)
```

With:

```python
        content = _render_full_coding_oob(request, conn, coder_id, source_index)
        response = HTMLResponse(content)
        response.headers["X-ACE-Toast"] = (
            "Source flagged" if new_status == "flagged" else "Source unflagged"
        )
        return response
```

NOTE: Use `X-ACE-Toast` header (NOT `HX-Trigger` with `ace-toast`). bridge.js line 47 already listens for `X-ACE-Toast` via `htmx:afterRequest` and calls `aceToast()`. The `HX-Trigger` `ace-toast` pattern is dead code in this codebase — nothing handles it.

- [ ] **Step 6: Add _announce for screen readers on flag toggle**

Add to the afterSettle header block (from Step 4):

```javascript
    if (target.id === "coding-header") {
      // Announce flag state for screen readers
      var flagBtn = document.getElementById("header-flag-btn");
      if (flagBtn) {
        var pressed = flagBtn.getAttribute("aria-pressed") === "true";
        // Only announce if this was a flag toggle (zone was header or text)
        if (_sidebarFocusState.zone === "header") {
          _announce(pressed ? "Source flagged" : "Source unflagged");
          flagBtn.focus();
        }
      }
      _sidebarFocusState.zone = null;
    }
```

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 8: Verify in browser**

- Click ? button → cheat sheet overlay opens
- Click flag icon → source gets flagged (orange chip appears), toast shows "Source flagged"
- Click flag chip → source gets unflagged (grey icon), toast shows "Source unflagged"
- Click flag a second time → still works (not broken by OOB swap)
- Click ? again → still works (not broken by OOB swap)
- Tab from text panel → lands on ACE link in header → Tab → search bar → Tab → tree → Tab → text panel
- Shift+Tab reverses
- While header button is focused, pressing letter keys does NOT trigger code shortcuts
- Shift+F from text panel still toggles flag

- [ ] **Step 9: Commit**

```bash
git add src/ace/static/js/bridge.js src/ace/routes/api.py
git commit -m "feat: header JS — delegated clicks, Tab zone, keydown guard, flag toast"
```

---

### Task 4: Cleanup & Verification

**Files:**
- Modify: `src/ace/static/css/coding.css`

- [ ] **Step 1: Verify old header CSS was fully removed in Task 2**

Search for any remaining references to old header classes:

```bash
grep -rn "ace-coding-header-back\|ace-coding-header-left\|ace-coding-header-title\|ace-coding-header-right\|ace-completion" src/ace/
```

If any CSS rules remain (Task 2 should have removed them), delete them now.

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 3: Full verification in browser**

Complete walkthrough:
1. Page loads → header shows: ACE (left), source name centred with position + greyed flag, ? (right)
2. Hover ACE → colour darkens
3. Click ACE → navigates to landing page
4. Navigate back to /code
5. Hover flag → icon darkens
6. Click flag → orange chip "⚑ Flagged" appears, toast confirms
7. Click flag again → grey icon returns, toast confirms
8. Shift+F from text panel → same toggle behaviour
9. Click ? → cheat sheet overlay
10. Press ? key → same overlay
11. Tab cycles: text → header → search → tree → text (Shift+Tab reverses)
12. Letter keys while header focused → no code shortcuts fire
13. Long source name truncates with ellipsis
14. Navigate to different source → header updates with new source name and position
15. After any action (annotate, undo, etc.), flag and ? buttons still respond to clicks

- [ ] **Step 4: Commit**

```bash
git add src/ace/static/css/coding.css
git commit -m "refactor: remove leftover old header CSS"
```
