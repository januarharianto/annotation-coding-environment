# Reorganisation Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a toggle mode to the coding page's left panel that enables full drag-and-drop reorganisation of codes across groups, and reordering of groups themselves.

**Architecture:** Two-level Sortable.js — outer Sortable for group wrapper reordering (handle on header), inner Sortables with shared `group` config for cross-group code dragging. The `code_list` `@ui.refreshable` function branches on `state["reorg_mode"]` to render either the existing per-group layout or the two-level reorg layout.

**Tech Stack:** NiceGUI, Sortable.js, SQLite, Python 3.12

**Spec:** `docs/superpowers/specs/2026-03-27-reorg-mode-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/ace/models/codebook.py` | Modify | Add `reorder_codes_with_groups()`, reserve "Ungrouped" name |
| `tests/test_models/test_codebook.py` | Modify | Tests for new model function + reserved name |
| `src/ace/static/js/bridge.js` | Modify | Two-level Sortable setup + reorg event payload |
| `src/ace/static/css/annotator.css` | Modify | Reorg-mode styles + drop insertion line |
| `src/ace/pages/coding.py` | Modify | Toggle button, reorg render path |
| `src/ace/pages/coding_shortcuts.py` | Modify | Handle reorg payload + Escape exits reorg + empty group notification |
| `src/ace/pages/coding_dialogs.py` | Modify | Validate reserved "Ungrouped" name |

---

### Task 1: Model — `reorder_codes_with_groups()`

**Files:**
- Modify: `src/ace/models/codebook.py`
- Modify: `tests/test_models/test_codebook.py`

- [ ] **Step 1: Write failing test**

Add `reorder_codes_with_groups` to the existing import block at the top of `tests/test_models/test_codebook.py`:

```python
from ace.models.codebook import (
    add_code,
    compute_codebook_hash,
    delete_code,
    export_codebook_to_csv,
    import_codebook_from_csv,
    import_selected_codes,
    list_codes,
    preview_codebook_csv,
    reorder_codes_with_groups,
    update_code,
)
```

Then add the test function at the end of the file:

```python
def test_reorder_codes_with_groups(tmp_db):
    conn = create_project(tmp_db, "Test")
    a = add_code(conn, "Alpha", "#FF0000", group_name="G1")
    b = add_code(conn, "Beta", "#00FF00", group_name="G1")
    c = add_code(conn, "Gamma", "#0000FF")

    # Move Gamma into G1, reorder: Gamma first, then Alpha, Beta ungrouped
    reorder_codes_with_groups(conn, [
        {"name": "G1", "code_ids": [c]},
        {"name": None, "code_ids": [a, b]},
    ])

    rows = list_codes(conn)
    assert rows[0]["id"] == c
    assert rows[0]["group_name"] == "G1"
    assert rows[0]["sort_order"] == 0
    assert rows[1]["id"] == a
    assert rows[1]["group_name"] is None
    assert rows[1]["sort_order"] == 1
    assert rows[2]["id"] == b
    assert rows[2]["group_name"] is None
    assert rows[2]["sort_order"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models/test_codebook.py::test_reorder_codes_with_groups -v`
Expected: FAIL with `ImportError: cannot import name 'reorder_codes_with_groups'`

- [ ] **Step 3: Write implementation**

Add to `src/ace/models/codebook.py` after the existing `reorder_codes` function:

```python
def reorder_codes_with_groups(conn: sqlite3.Connection, groups: list[dict]) -> None:
    """Reorder codes and update group membership in one transaction.

    groups: [{"name": str | None, "code_ids": [str, ...]}, ...]
    """
    sort_order = 0
    for group in groups:
        group_name = group["name"]
        for code_id in group["code_ids"]:
            conn.execute(
                "UPDATE codebook_code SET sort_order = ?, group_name = ? WHERE id = ?",
                (sort_order, group_name, code_id),
            )
            sort_order += 1
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models/test_codebook.py::test_reorder_codes_with_groups -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ace/models/codebook.py tests/test_models/test_codebook.py
git commit -m "feat: add reorder_codes_with_groups model function"
```

---

### Task 2: Validate reserved "Ungrouped" group name

**Files:**
- Modify: `src/ace/models/codebook.py`
- Modify: `src/ace/pages/coding_dialogs.py`
- Modify: `tests/test_models/test_codebook.py`

- [ ] **Step 1: Write failing test**

Add at the end of `tests/test_models/test_codebook.py`:

```python
def test_add_code_ungrouped_group_name_rejected(tmp_db):
    """The name 'Ungrouped' is reserved and should not be used as a group name."""
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Alpha", "#FF0000", group_name="Ungrouped")
    row = conn.execute("SELECT group_name FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    # "Ungrouped" should be stored as NULL (ungrouped)
    assert row["group_name"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models/test_codebook.py::test_add_code_ungrouped_group_name_rejected -v`
Expected: FAIL — `assert "Ungrouped" is None`

- [ ] **Step 3: Implement in model layer**

In `src/ace/models/codebook.py`, modify `add_code()` — add after the function signature, before `now = ...`:

```python
    if group_name and group_name.strip().lower() == "ungrouped":
        group_name = None
```

Also modify `update_code()` — replace the existing `if group_name is not _UNSET:` block:

```python
    if group_name is not _UNSET:
        if isinstance(group_name, str) and group_name.strip().lower() == "ungrouped":
            group_name = ""
        updates.append("group_name = ?")
        params.append(group_name if group_name != "" else None)
```

- [ ] **Step 4: Update the "New Group" dialog validation**

In `src/ace/pages/coding_dialogs.py`, modify the `_create` function inside `open_new_group_dialog`:

```python
        def _create():
            name = name_input.value.strip()
            if not name:
                return
            if name.lower() == "ungrouped":
                ui.notify("'Ungrouped' is reserved.", type="warning", position="bottom")
                return
            dlg.close()
            on_create(name)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_models/test_codebook.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/ace/models/codebook.py src/ace/pages/coding_dialogs.py tests/test_models/test_codebook.py
git commit -m "feat: reserve 'Ungrouped' as group name, validate in model and dialog"
```

---

### Task 3: CSS for reorg mode

**Files:**
- Modify: `src/ace/static/css/annotator.css`

- [ ] **Step 1: Add reorg-mode styles**

Append to `src/ace/static/css/annotator.css`:

```css
/* ── Reorg mode ──────────────────────────────────────────── */
.ace-reorg-container {
    display: flex;
    flex-direction: column;
    width: 100%;
}
.ace-reorg-group {
    flex-shrink: 0;
}
.ace-reorg-group.ace-drag-ghost {
    opacity: 0.4;
}
.ace-reorg-code-list {
    min-height: 8px;
}
.ace-reorg-code-list .ace-code-row {
    cursor: grab;
}
.ace-reorg-code-list .ace-code-row.ace-drag-ghost {
    opacity: 0.4;
}
.ace-reorg-btn-active {
    background: #eeeeee !important;
    border-radius: 4px;
}
.ace-sortable-chosen {
    border-top: 2px solid #bdbdbd;
}
```

Note: `#eeeeee` matches Quasar's `bg-grey-3` per the spec. The `ace-sortable-chosen` class provides the drop insertion line.

- [ ] **Step 2: Commit**

```bash
git add src/ace/static/css/annotator.css
git commit -m "style: add reorg mode CSS classes and drop insertion line"
```

---

### Task 4: JavaScript — two-level Sortable for reorg mode

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Replace the `setupCodeListSortable` function**

Replace the entire `setupCodeListSortable` function in `src/ace/static/js/bridge.js` with:

```javascript
  function setupCodeListSortable() {
    var _sortables = [];
    var _containerSignature = "";
    var _dragging = false;

    function collectAllCodeIds() {
      var containers = document.querySelectorAll(".ace-code-list");
      var ids = [];
      for (var c = 0; c < containers.length; c++) {
        var items = containers[c].querySelectorAll("[data-code-id]");
        for (var i = 0; i < items.length; i++) {
          ids.push(items[i].dataset.codeId);
        }
      }
      return ids;
    }

    function collectReorgPayload() {
      var container = document.querySelector(".ace-reorg-container");
      if (!container) return null;
      var groups = [];
      var wrappers = container.querySelectorAll(":scope > .ace-reorg-group");
      for (var w = 0; w < wrappers.length; w++) {
        var header = wrappers[w].querySelector(".ace-group-header");
        // Named groups have data-group-name; ungrouped header has none → null
        var groupName = header && header.hasAttribute("data-group-name")
          ? header.getAttribute("data-group-name")
          : null;
        var codeList = wrappers[w].querySelector(".ace-reorg-code-list");
        var codeIds = [];
        if (codeList) {
          var items = codeList.querySelectorAll("[data-code-id]");
          for (var i = 0; i < items.length; i++) {
            codeIds.push(items[i].dataset.codeId);
          }
        }
        groups.push({ name: groupName, code_ids: codeIds });
      }
      return { groups: groups };
    }

    function initSortable() {
      if (_dragging) return;

      var reorgContainer = document.querySelector(".ace-reorg-container");
      var normalContainers = document.querySelectorAll(".ace-code-list");

      // Build signature
      var sig = "";
      if (reorgContainer) {
        sig = "reorg:" + reorgContainer.id + ":" + reorgContainer.children.length + ";";
        var innerLists = reorgContainer.querySelectorAll(".ace-reorg-code-list");
        for (var i = 0; i < innerLists.length; i++) {
          sig += innerLists[i].id + ":" + innerLists[i].children.length + ";";
        }
      } else {
        for (var c = 0; c < normalContainers.length; c++) {
          sig += normalContainers[c].id + ":" + normalContainers[c].children.length + ";";
        }
      }
      if (sig === _containerSignature) return;
      _containerSignature = sig;

      // Destroy old instances
      for (var s = 0; s < _sortables.length; s++) {
        _sortables[s].destroy();
      }
      _sortables = [];

      if (reorgContainer) {
        // ── Reorg mode: two-level Sortable ──
        // Outer: reorder group wrappers
        _sortables.push(Sortable.create(reorgContainer, {
          animation: 150,
          handle: ".ace-group-header",
          ghostClass: "ace-drag-ghost",
          chosenClass: "ace-sortable-chosen",
          onStart: function () { _dragging = true; },
          onEnd: function () {
            _dragging = false;
            var payload = collectReorgPayload();
            if (payload) emitEvent("codes_reordered", payload);
          },
        }));

        // Inner: cross-group code dragging
        var innerLists = reorgContainer.querySelectorAll(".ace-reorg-code-list");
        for (var i = 0; i < innerLists.length; i++) {
          _sortables.push(Sortable.create(innerLists[i], {
            animation: 150,
            group: { name: "codes", pull: true, put: true },
            ghostClass: "ace-drag-ghost",
            chosenClass: "ace-sortable-chosen",
            fallbackOnBody: true,
            swapThreshold: 0.65,
            onStart: function () { _dragging = true; },
            onEnd: function () {
              _dragging = false;
              var payload = collectReorgPayload();
              if (payload) emitEvent("codes_reordered", payload);
            },
          }));
        }
      } else {
        // ── Normal mode: per-group Sortable (existing behaviour) ──
        for (var c = 0; c < normalContainers.length; c++) {
          var container = normalContainers[c];
          if (!container.querySelector(".ace-drag-handle")) continue;

          _sortables.push(Sortable.create(container, {
            animation: 150,
            handle: ".ace-drag-handle",
            ghostClass: "ace-drag-ghost",
            onEnd: function () {
              emitEvent("codes_reordered", { code_ids: collectAllCodeIds() });
            },
          }));
        }
      }
    }

    new MutationObserver(initSortable).observe(document.body, {
      childList: true,
      subtree: true,
    });
  }
```

Key differences from original plan (audit fixes):
- `collectReorgPayload` uses `hasAttribute`/`getAttribute` instead of `dataset.groupName || null` for explicit null handling
- Inner Sortables include `fallbackOnBody: true` and `swapThreshold: 0.65` (SortableJS recommendation for nested instances)
- Both outer and inner use `chosenClass: "ace-sortable-chosen"` for the drop insertion line

- [ ] **Step 2: Verify no JS syntax errors**

Run: `node -c src/ace/static/js/bridge.js` (or open the coding page in browser and check console for errors)

- [ ] **Step 3: Commit**

```bash
git add src/ace/static/js/bridge.js
git commit -m "feat: two-level Sortable for reorg mode with dragging guard"
```

---

### Task 5: Python event handler — support reorg payload

**Files:**
- Modify: `src/ace/pages/coding_shortcuts.py`

- [ ] **Step 1: Update the import, handler, and Escape**

In `src/ace/pages/coding_shortcuts.py`, update the import:

```python
from ace.models.codebook import reorder_codes, reorder_codes_with_groups
```

Replace the `_on_codes_reordered` function:

```python
    def _on_codes_reordered(e):
        groups = e.args.get("groups")
        if groups:
            # Reorg mode: nested payload with group names
            # Detect emptied groups for notification
            old_group_names = {c["group_name"] for c in codes if c["group_name"]}
            reorder_codes_with_groups(conn, groups)
            refresh_codes_fn()
            new_group_names = {c["group_name"] for c in codes if c["group_name"]}
            for gone in old_group_names - new_group_names:
                ui.notify(f"'{gone}' group removed (no remaining codes).", type="info", position="bottom")
        else:
            # Normal mode: flat code_ids list
            code_ids = e.args.get("code_ids", [])
            if code_ids:
                reorder_codes(conn, code_ids)
            refresh_codes_fn()
        code_list_refresh()
```

Replace the `_on_shortcut_escape` function:

```python
    def _on_shortcut_escape(_e):
        if state.get("reorg_mode"):
            state["reorg_mode"] = False
            refresh_codes_fn()
            code_list_refresh()
            return
        if grid_container.visible:
            grid_container.set_visibility(False)
            return
        state["pending_selection"] = None
```

Note: `refresh_codes_fn()` is called on Escape exit to ensure in-memory codes match DB after exiting reorg mode.

- [ ] **Step 2: Commit**

```bash
git add src/ace/pages/coding_shortcuts.py
git commit -m "feat: handle reorg payload, empty group notification, Escape exits reorg"
```

---

### Task 6: Reorg toggle button and render path

**Files:**
- Modify: `src/ace/pages/coding.py`

- [ ] **Step 1: Add the reorg toggle button**

In `src/ace/pages/coding.py`, after the sort button and its tooltip (around line 215), add within the same header row:

```python
                def _toggle_reorg():
                    entering = not state.get("reorg_mode", False)
                    state["reorg_mode"] = entering
                    if entering:
                        state["sort_codes"] = False
                    _refresh_codes()
                    code_list.refresh()

                reorg_btn = ui.button(
                    icon="swap_vert",
                    on_click=_toggle_reorg,
                ).props("flat dense size=sm").classes(
                    "text-grey-7"
                ).tooltip("Reorganise codes and groups")
```

Note: `_refresh_codes()` is called on both enter AND exit to ensure in-memory codes match DB state.

- [ ] **Step 2: Add the reorg render path in `code_list()`**

In the `code_list()` refreshable function, after the `has_groups` check (around line 606), add a branch for reorg mode. Insert this block right after the `has_groups` computation and before the existing `if not has_groups:` block:

```python
                reorg = state.get("reorg_mode", False)

                # Show/hide reorg and sort buttons based on mode and groups
                reorg_btn.set_visibility(has_groups)
                if reorg and has_groups:
                    reorg_btn.classes(add="ace-reorg-btn-active")
                else:
                    reorg_btn.classes(remove="ace-reorg-btn-active")
                    if reorg:
                        # Groups were removed while in reorg mode
                        state["reorg_mode"] = False
                        reorg = False

                if reorg and has_groups:
                    # ── Reorg render path ──────────────────────────────
                    # Build ordered groups (same logic as normal mode)
                    groups_dict: dict[str | None, list] = {}
                    grp_order: list[str | None] = []
                    for code in codes:
                        gn = code["group_name"] or None
                        if gn not in groups_dict:
                            groups_dict[gn] = []
                            grp_order.append(gn)
                        groups_dict[gn].append(code)

                    named_groups = [(k, groups_dict[k]) for k in grp_order if k is not None]
                    ungrouped_codes = groups_dict.get(None, [])

                    # Reorder codes list for shortcut consistency
                    display_order = []
                    for _, grp_codes in named_groups:
                        display_order.extend(grp_codes)
                    display_order.extend(ungrouped_codes)
                    codes.clear()
                    codes.extend(display_order)
                    codes_by_id.clear()
                    codes_by_id.update({c["id"]: c for c in codes})

                    global_idx = 0
                    with ui.element("div").classes("ace-reorg-container"):
                        for group_name, grp_codes in named_groups:
                            with ui.element("div").classes("ace-reorg-group"):
                                safe_name = html.escape(group_name, quote=True)
                                with ui.element("div").classes("ace-group-header").props(
                                    f'data-group-name="{safe_name}"'
                                ).style("cursor: grab;"):
                                    ui.icon("drag_indicator", size="xs").classes("text-grey-5")
                                    ui.label(group_name)
                                with ui.element("div").classes("ace-reorg-code-list"):
                                    for code in grp_codes:
                                        _render_code_row(code, _shortcut_label(global_idx), sorting=False, reorg=True)
                                        global_idx += 1

                        # Ungrouped section — always shown as drop target
                        with ui.element("div").classes("ace-reorg-group"):
                            with ui.element("div").classes("ace-group-header").style("cursor: grab;"):
                                ui.icon("drag_indicator", size="xs").classes("text-grey-5")
                                ui.label("Ungrouped")
                            with ui.element("div").classes("ace-reorg-code-list"):
                                for code in ungrouped_codes:
                                    _render_code_row(code, _shortcut_label(global_idx), sorting=False, reorg=True)
                                    global_idx += 1

                    return
```

Note: `html.escape(group_name, quote=True)` prevents XSS via group names with quotes. The `import html` is already at the top of coding.py. The Ungrouped header has no `data-group-name` attribute — the JS explicitly checks `hasAttribute` and returns `null` for it.

- [ ] **Step 3: Update `_render_code_row` to accept `reorg` parameter**

Modify the function signature and body:

```python
            def _render_code_row(code, shortcut: str, sorting: bool, pad_left: str = "2px 4px", reorg: bool = False):
                colour = code["colour"] or "#999999"

                async def _click_apply(_e, c=code):
                    if state.get("reorg_mode"):
                        return  # Suppress click-to-apply in reorg mode
                    await _apply_code(c)

                with ui.row().classes(
                    "items-center full-width no-wrap ace-hover-row ace-code-row"
                ).style(
                    f"gap: 4px; padding: {pad_left}; flex-shrink: 0; overflow: hidden;"
                    f" border-left: 4px solid {colour};"
                ) as row:
                    row.props(f'data-code-id={code["id"]}')
                    if not sorting and not reorg:
                        ui.icon("drag_indicator", size="xs").classes(
                            "ace-drag-handle text-grey-5"
                        )
                    lbl = ui.label(code["name"]).classes(
                        "text-body2 col ellipsis" + ("" if reorg else " cursor-pointer")
                    ).style(
                        "min-width: 0; line-height: 1.4;"
                    ).on("click", _click_apply)
                    if shortcut:
                        ui.label(shortcut).classes("ace-keycap")
                    with ui.button(icon="more_horiz").props(
                        "flat round dense size=xs"
                    ).classes("ace-hover-action"):
                        with ui.menu():
                            ui.menu_item(
                                "Rename",
                                on_click=lambda _e, c=code: open_rename_dialog(conn, rename_dialog, c, _refresh_all),
                            )
                            ui.menu_item(
                                "Change colour",
                                on_click=lambda _e, c=code: open_colour_dialog(conn, colour_dialog, c, _refresh_all),
                            )
                            ui.separator()
                            ui.menu_item(
                                "Move to Group",
                                on_click=lambda _e, c=code: _show_move_to_group(c),
                            )
                            ui.separator()
                            ui.menu_item(
                                "Delete",
                                on_click=lambda _e, c=code: open_delete_dialog(conn, delete_dialog, c, _refresh_all),
                            )
```

Note: The context menu (including "Move to Group") is kept in reorg mode per the spec. Click-to-apply is suppressed via the early return in `_click_apply`, not by hiding the menu.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -x -q`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/ace/pages/coding.py
git commit -m "feat: reorg toggle button and two-level render path"
```

---

### Task 7: Manual integration test

**Files:** None (manual verification)

- [ ] **Step 1: Start the server**

Run: `uv run ace`

- [ ] **Step 2: Verify reorg button visibility**

Open a project with grouped codes. Confirm:
- The swap_vert icon appears next to the sort button
- It does NOT appear when no groups exist (open a project with flat codes)

- [ ] **Step 3: Enter reorg mode**

Click the reorg button. Confirm:
- Button gets highlighted background (`#eeeeee`)
- Drag handles on individual codes disappear
- Group headers show drag_indicator icons
- All groups are expanded (regardless of previous collapse state)
- "Ungrouped" section appears with header
- Sort button still visible but clicking it exits reorg mode (mutual exclusion)

- [ ] **Step 4: Drag a code between groups**

Drag a code from one group into another group's code list. Confirm:
- The code moves visually during drag with insertion line visible
- After drop, the page re-renders with the code in its new group
- Keyboard shortcuts update to match new positions

- [ ] **Step 5: Drag a group header**

Drag a group header to reorder it among other groups. Confirm:
- The entire group (header + all codes) moves as a unit
- After drop, the page re-renders with groups in new order

- [ ] **Step 6: Drag all codes out of a group**

Drag every code out of a group. Confirm:
- The empty group disappears after re-render
- A notification appears: "'GroupName' group removed (no remaining codes)."

- [ ] **Step 7: Context menu in reorg mode**

Right-click (or click "...") on a code row. Confirm:
- Context menu appears with Rename, Change colour, Move to Group, Delete
- "Move to Group" works and triggers re-render with Sortable re-initialisation

- [ ] **Step 8: Exit reorg mode**

Press Escape or click the reorg button again. Confirm:
- Drag handles reappear on individual codes
- Click-to-apply works again on code labels
- Previously collapsed groups are still collapsed
- Full context menus visible

- [ ] **Step 9: Commit all remaining fixes**

If any issues were found and fixed during manual testing:

```bash
git add -A
git commit -m "fix: address reorg mode integration test findings"
```
