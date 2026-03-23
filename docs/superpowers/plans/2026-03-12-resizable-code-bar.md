# Resizable Code Bar Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed-width code bar with a resizable splitter, persisting width across sessions, with double-click-to-reset.

**Architecture:** Swap the `ui.row()` two-pane container (coding.py:238-240) for `ui.splitter()` in pixel mode. Add a delegated dblclick listener in bridge.js for reset. Persist width to `app.storage.general`.

**Tech Stack:** NiceGUI `ui.splitter()` (Quasar `q-splitter`), bridge.js, annotator.css

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/ace/pages/coding.py` | Modify lines 237-246, 345-346 | Replace `ui.row()` with `ui.splitter()`, wire persistence + reset |
| `src/ace/static/js/bridge.js` | Add function + call in `initAll()` | Delegated dblclick on separator |
| `src/ace/static/css/annotator.css` | Add ~3 lines | Separator styling |

---

## Task 1: Replace layout container with ui.splitter()

**Files:**
- Modify: `src/ace/pages/coding.py:237-246` (container open), `src/ace/pages/coding.py:345-346` (right panel open)

- [ ] **Step 1: Replace the ui.row() container with ui.splitter()**

In `coding.py`, replace lines 237-240:

```python
    # ── Main two-pane container ──────────────────────────────────────
    with ui.row().classes("full-width no-wrap col").style(
        "overflow: hidden;"
    ):
```

with:

```python
    # ── Main two-pane container (resizable) ─────────────────────────
    stored_width = app.storage.general.get("code_bar_width", 280)
    splitter = ui.splitter(value=stored_width, limits=(180, 600)).props(
        'unit="px"'
    ).classes("full-width col").style("overflow: hidden;")
    with splitter:
```

- [ ] **Step 2: Wrap left panel in splitter.before, remove fixed width/border**

Replace lines 242-246:

```python
        # ── Left Panel (280px) ───────────────────────────────────────
        with ui.column().classes("q-pa-md ace-no-scrollbar").style(
            "width: 280px; min-width: 280px; overflow-y: auto; "
            "border-right: 1px solid #bdbdbd; height: 100%;"
        ):
```

with:

```python
        # ── Left Panel (code bar) ───────────────────────────────────
        with splitter.before:
          with ui.column().classes("q-pa-md ace-no-scrollbar").style(
              "overflow-y: auto; height: 100%;"
          ):
```

- [ ] **Step 3: Wrap right panel in splitter.after**

Replace line 345-346:

```python
        # ── Right Panel (flex) ───────────────────────────────────────
        with ui.column().classes("col q-pa-md").style("overflow-y: auto;"):
```

with:

```python
        # ── Right Panel (flex) ───────────────────────────────────────
        with splitter.after:
          with ui.column().classes("col q-pa-md").style("overflow-y: auto;"):
```

- [ ] **Step 4: Add persistence callback**

After the splitter creation (after `with splitter:`), add:

```python
    def _on_splitter_change(e):
        app.storage.general["code_bar_width"] = e.value

    splitter.on_value_change(_on_splitter_change)
```

- [ ] **Step 5: Add reset handler**

Below the persistence callback, add:

```python
    def _reset_code_bar_width():
        splitter.value = 280
        app.storage.general.pop("code_bar_width", None)

    ui.on("code_bar_reset", lambda _: _reset_code_bar_width())
```

- [ ] **Step 6: Run the app and verify layout**

Run: `uv run ace`

Verify:
- Two-pane layout renders correctly
- Code bar is resizable by dragging the separator
- Drag stops at 180px min and 600px max
- Width persists after page reload
- All existing code bar content (codes, input, sort, drag reorder) works

- [ ] **Step 7: Commit**

```bash
git add src/ace/pages/coding.py
git commit -m "feat: resizable code bar using ui.splitter()"
```

---

## Task 2: Add double-click reset in bridge.js

**Files:**
- Modify: `src/ace/static/js/bridge.js` (add function + register in initAll)

- [ ] **Step 1: Add setupSplitterReset function**

In `bridge.js`, add before the `initAll()` function (before line 266):

```javascript
  // ── Splitter double-click reset ─────────────────────────────────
  function setupSplitterReset() {
    document.addEventListener("dblclick", function (e) {
      if (!e.target.closest(".q-splitter__separator")) return;
      e.preventDefault();
      emitEvent("code_bar_reset", {});
    });
  }
```

- [ ] **Step 2: Register in initAll()**

In `initAll()` (line 266-272), add `setupSplitterReset();`:

```javascript
  function initAll() {
    setupSelectionListener();
    setupAnnotationClickListener();
    setupKeyboardShortcuts();
    setupCodeListSortable();
    setupGridClickListener();
    setupSplitterReset();
  }
```

- [ ] **Step 3: Verify double-click reset**

Run: `uv run ace`

Verify:
- Drag code bar to a non-default width
- Double-click the separator → width snaps back to 280px
- Reload page → width is 280px (storage cleared)

- [ ] **Step 4: Commit**

```bash
git add src/ace/static/js/bridge.js
git commit -m "feat: double-click splitter separator to reset code bar width"
```

---

## Task 3: Style the separator

**Files:**
- Modify: `src/ace/static/css/annotator.css` (append rules)

- [ ] **Step 1: Add separator styling**

Append to `annotator.css`:

```css
.q-splitter__separator {
    background: #bdbdbd;
    width: 1px !important;
}
.q-splitter__separator:hover {
    background: #9e9e9e;
    width: 3px !important;
}
```

- [ ] **Step 2: Verify styling**

Run: `uv run ace`

Verify:
- Separator appears as a thin `#bdbdbd` line (matches existing borders)
- On hover, separator widens slightly and darkens — clear affordance for dragging
- No visual double-border with the code bar

- [ ] **Step 3: Commit**

```bash
git add src/ace/static/css/annotator.css
git commit -m "style: minimal separator styling for resizable code bar"
```
