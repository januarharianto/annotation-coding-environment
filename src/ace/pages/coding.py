"""New two-pane coding interface with inline code creation."""

import hashlib
import json
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from nicegui import app, events, ui

from ace.db.connection import checkpoint_and_close, open_project
from ace.models.annotation import (
    get_annotations_for_source,
)
from ace.models.assignment import get_assignments_for_coder
from ace.models.codebook import add_code, export_codebook_to_csv, import_selected_codes, list_codes, preview_codebook_csv, update_code
from ace.models.coder import add_coder, list_coders, update_coder
from ace.models.project import get_project
from ace.pages.header import build_header
from ace.models.source import get_source, list_sources
from ace.pages.coding_actions import (
    apply_code,
    auto_transition,
    delete_annotation_action,
    navigate_to,
    render_text,
    toggle_flag,
)
from ace.pages.coding_bottom_bar import build_bottom_bar
from ace.pages.coding_dialogs import open_colour_dialog, open_delete_dialog, open_new_group_dialog, open_rename_dialog
from ace.pages.coding_render import render_annotated_text  # noqa: F401 — re-exported for tests
from ace.pages.coding_shortcuts import register_shortcuts
from ace.services.palette import next_colour
from ace.services.undo import UndoManager

_STATIC_DIR = Path(__file__).parent.parent / "static"
_BRIDGE_HASH = hashlib.md5((_STATIC_DIR / "js" / "bridge.js").read_bytes()).hexdigest()[:8]
_CSS_HASH = hashlib.md5((_STATIC_DIR / "css" / "annotator.css").read_bytes()).hexdigest()[:8]
_SORTABLE_HASH = hashlib.md5((_STATIC_DIR / "js" / "Sortable.min.js").read_bytes()).hexdigest()[:8]



# ---------------------------------------------------------------------------
# Status icon helper
# ---------------------------------------------------------------------------

_STATUS_ICONS = {
    "pending": ("radio_button_unchecked", "#757575"),
    "in_progress": ("edit", "#546e7a"),
    "complete": ("check_circle", "#2e7d32"),
    "flagged": ("flag", "#c62828"),
}


# ---------------------------------------------------------------------------
# Ensure assignments exist for all sources
# ---------------------------------------------------------------------------

def _ensure_assignments(conn, coder_id, sources):
    for src in sources:
        existing = conn.execute(
            "SELECT id FROM assignment WHERE source_id = ? AND coder_id = ?",
            (src["id"], coder_id),
        ).fetchone()
        if not existing:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO assignment (id, source_id, coder_id, status, assigned_at, updated_at) "
                "VALUES (?, ?, ?, 'pending', ?, ?)",
                (uuid.uuid4().hex, src["id"], coder_id, now, now),
            )
    conn.commit()


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build(conn: sqlite3.Connection) -> None:
    """Build the two-pane coding interface."""

    project = get_project(conn)
    build_header(project_name=project["name"] if project else "ACE", conn=conn)

    # Resolve coder — use stored name, or prompt if unknown
    stored_name = app.storage.general.get("coder_name")
    coders = list_coders(conn)
    if not coders:
        coder_id = add_coder(conn, stored_name or "default")
    else:
        coder_id = coders[0]["id"]
        # Sync coder name with stored name
        if stored_name and coders[0]["name"] != stored_name:
            update_coder(conn, coder_id, stored_name)

    sources = list_sources(conn)
    if not sources:
        ui.navigate.to("/import")
        return

    _ensure_assignments(conn, coder_id, sources)

    codes = list_codes(conn)
    codes_by_id = {c["id"]: c for c in codes}

    assignments = get_assignments_for_coder(conn, coder_id)
    if not assignments:
        ui.label("No sources found.").classes("text-h6 q-pa-md")
        return

    # State tracking
    state = {
        "current_index": 0,
        "pending_selection": None,
    }
    undo_mgr = UndoManager()

    # Find first pending/in_progress source
    for i, a in enumerate(assignments):
        if a["status"] in ("pending", "in_progress"):
            state["current_index"] = i
            break

    def current_assignment():
        return assignments[state["current_index"]]

    def current_source_id():
        return current_assignment()["source_id"]

    def _reload_assignments():
        fresh = get_assignments_for_coder(conn, coder_id)
        assignments.clear()
        assignments.extend(fresh)

    def _refresh_codes():
        """Reload codes from DB and rebuild codes_by_id."""
        fresh = list_codes(conn)
        codes.clear()
        codes.extend(fresh)
        codes_by_id.clear()
        codes_by_id.update({c["id"]: c for c in codes})

    # ── Layout ────────────────────────────────────────────────────────
    ui.add_head_html(f'<link rel="stylesheet" href="/static/css/annotator.css?v={_CSS_HASH}">')
    ui.add_head_html(f'<script src="/static/js/Sortable.min.js?v={_SORTABLE_HASH}"></script>')
    ui.add_head_html(f'<script src="/static/js/bridge.js?v={_BRIDGE_HASH}" defer></script>')
    ui.add_head_html(
        '<style>'
        'html, body, #app, .q-layout, .q-page-container { height: 100vh; } '
        'html, body { overflow: hidden; } '
        '.q-page { display: flex; flex-direction: column; height: 100%; } '
        '.q-page > .nicegui-content { flex: 1; min-height: 0; display: flex; flex-direction: column; }'
        '</style>'
    )

    annotation_info_dialog = ui.dialog()
    rename_dialog = ui.dialog()
    colour_dialog = ui.dialog()
    delete_dialog = ui.dialog()
    move_dialog = ui.dialog()
    new_group_dialog = ui.dialog()

    # ── Main two-pane container (resizable) ─────────────────────────
    _DEFAULT_WIDTH = 280
    _STORAGE_KEY = "code_bar_width"

    stored_width = app.storage.general.get(_STORAGE_KEY, _DEFAULT_WIDTH)
    splitter = ui.splitter(value=stored_width, limits=(180, 600)).props(
        'unit="px"'
    ).classes("full-width col").style("overflow: hidden;")

    def _on_splitter_change(e):
        width = round(e.value)
        if width == _DEFAULT_WIDTH:
            app.storage.general.pop(_STORAGE_KEY, None)
        elif app.storage.general.get(_STORAGE_KEY) != width:
            app.storage.general[_STORAGE_KEY] = width

    splitter.on_value_change(_on_splitter_change)

    def _reset_code_bar_width():
        splitter.value = _DEFAULT_WIDTH

    ui.on("code_bar_reset", lambda _: _reset_code_bar_width())

    with splitter:

        # ── Left Panel (code bar) ───────────────────────────────────
        with splitter.before:
          with ui.column().classes("q-pa-md ace-no-scrollbar").style(
              "overflow-y: auto; height: 100%;"
              " width: 100%; min-width: 0;"
          ):
            with ui.row().classes("items-center full-width q-mt-sm").style("flex-shrink: 0;"):
                ui.label("Codes").classes("text-subtitle1 text-weight-medium")
                ui.space()

                def _toggle_sort():
                    state["sort_codes"] = not state.get("sort_codes", False)
                    if state["sort_codes"]:
                        has_groups = any(c["group_name"] for c in codes)
                        if has_groups:
                            codes.sort(key=lambda c: (c["group_name"] or "", c["name"].lower()))
                        else:
                            codes.sort(key=lambda c: c["name"].lower())
                    else:
                        _refresh_codes()  # restore DB order
                    code_list.refresh()

                ui.button(
                    icon="sort_by_alpha",
                    on_click=_toggle_sort,
                ).props("flat dense size=sm").classes(
                    "text-grey-7"
                ).tooltip("Sort codes by name")

                # Import / Export menu
                import_dialog = ui.dialog()

                def _import_codes():
                    upload_el.run_method("pickFiles")

                def _export_codes():
                    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, prefix="ace_codebook_")
                    tmp.close()
                    count = export_codebook_to_csv(conn, tmp.name)
                    if count == 0:
                        ui.notify("No codes to export.", type="info", position="bottom")
                        Path(tmp.name).unlink(missing_ok=True)
                        return
                    ui.download(tmp.name, "codes.csv")

                with ui.button(icon="more_vert").props("flat round dense size=sm").classes("text-grey-7"):
                    with ui.menu():
                        ui.menu_item("Import Codes", on_click=lambda: _import_codes())
                        ui.menu_item("Export CSV", on_click=lambda: _export_codes()).props(
                            "disable" if not codes else ""
                        )

                async def _handle_upload(e: events.UploadEventArguments):
                    upload_el.reset()
                    try:
                        content = await e.file.read()
                        tmp_dir = Path(tempfile.mkdtemp(prefix="ace_import_"))
                        tmp_path = tmp_dir / e.file.name
                        tmp_path.write_bytes(content)
                        preview = preview_codebook_csv(conn, str(tmp_path))
                        tmp_path.unlink(missing_ok=True)
                        tmp_dir.rmdir()
                    except ValueError as exc:
                        ui.notify(str(exc), type="negative", position="bottom")
                        return
                    except Exception as exc:
                        ui.notify(f"Could not read CSV file: {exc}", type="negative", position="bottom")
                        return

                    if not preview:
                        ui.notify("No valid codes found (check CSV format).", type="info", position="bottom")
                        return

                    _show_import_dialog(preview)

                def _show_import_dialog(preview):
                    selected = {}
                    checkboxes = {}
                    group_checkboxes = {}  # group_name -> ui.checkbox
                    new_codes = [p for p in preview if not p["exists"]]
                    existing_codes = [p for p in preview if p["exists"]]
                    import_dialog.clear()

                    # Detect whether any code has a group
                    has_groups = any(p.get("group_name") for p in preview)

                    # Group codes by group_name (preserving insertion order)
                    def _group_by(codes):
                        grouped = {}
                        for p in codes:
                            grp = p.get("group_name") or ""
                            grouped.setdefault(grp, []).append(p)
                        return grouped

                    grouped_new = _group_by(new_codes) if has_groups else {"": new_codes}
                    grouped_existing = _group_by(existing_codes) if has_groups else {"": existing_codes}

                    def _update_group_checkbox(grp):
                        """Update a group header checkbox to reflect its children."""
                        if grp not in group_checkboxes:
                            return
                        codes_in_grp = grouped_new.get(grp, [])
                        checked = sum(1 for p in codes_in_grp if selected.get(p["name"]))
                        total = len(codes_in_grp)
                        gcb = group_checkboxes[grp]
                        if checked == total:
                            gcb.value = True
                            gcb.props(remove="indeterminate")
                        elif checked == 0:
                            gcb.value = False
                            gcb.props(remove="indeterminate")
                        else:
                            gcb.value = False
                            gcb.props("indeterminate")

                    def _toggle_group(grp, value):
                        """Toggle all codes in a group on/off."""
                        for p in grouped_new.get(grp, []):
                            selected[p["name"]] = value
                            if p["name"] in checkboxes:
                                checkboxes[p["name"]].value = value
                        gcb = group_checkboxes[grp]
                        gcb.props(remove="indeterminate")
                        gcb.value = value
                        _update_btn()
                        _update_toggle_link()

                    def _on_group_checkbox(grp, e):
                        """Handle group checkbox click — indeterminate→all, checked→none, unchecked→all."""
                        _toggle_group(grp, e.value)

                    with import_dialog, ui.card().classes("q-pa-md").style("min-width: 340px;"):
                        ui.label("Import Codes").classes("text-subtitle1 text-weight-medium q-mb-sm")

                        # Summary line
                        if existing_codes:
                            ui.label(
                                f"{len(new_codes)} new \u00b7 {len(existing_codes)} already in project"
                            ).classes("text-caption text-grey-7 q-mb-sm")

                        if not new_codes:
                            ui.label("All codes in this file already exist.").classes(
                                "text-body2 text-grey-6 q-mb-sm"
                            )

                        with ui.column().classes("full-width").style("max-height: 300px; overflow-y: auto;"):
                            # New codes section
                            if new_codes:
                                with ui.row().classes("items-center full-width justify-between q-mb-xs"):
                                    ui.label(f"New codes ({len(new_codes)})").classes(
                                        "text-caption text-weight-medium text-grey-8"
                                    )
                                    def _on_toggle_link():
                                        all_checked = all(selected.get(p["name"]) for p in new_codes)
                                        _toggle_all(not all_checked)

                                    toggle_link = ui.button(
                                        "none", on_click=_on_toggle_link,
                                    ).props("flat dense no-caps size=xs").classes("text-caption text-grey-6")

                                for grp, codes_in_grp in grouped_new.items():
                                    # Group header (only for named groups)
                                    if grp:
                                        gcb = ui.checkbox(
                                            grp.upper(),
                                            value=True,
                                            on_change=lambda e, g=grp: _on_group_checkbox(g, e),
                                        ).classes("text-weight-medium").style(
                                            "font-size: 12px; color: #757575;"
                                        )
                                        group_checkboxes[grp] = gcb

                                    indent = "padding-left: 24px;" if grp and has_groups else ""
                                    for p in codes_in_grp:
                                        selected[p["name"]] = True
                                        with ui.row().classes("items-center full-width no-wrap").style(indent):
                                            ui.element("div").style(
                                                f"background: {p['colour']}; width: 14px; height: 14px; "
                                                "border-radius: 50%; flex-shrink: 0;"
                                            )
                                            cb = ui.checkbox(
                                                p["name"],
                                                value=True,
                                                on_change=lambda e, name=p["name"], g=grp: _toggle(name, e.value, g),
                                            )
                                            checkboxes[p["name"]] = cb

                            # Existing codes section (collapsed)
                            if existing_codes:
                                with ui.expansion(
                                    f"Already in project ({len(existing_codes)})",
                                ).props("dense header-class='text-caption text-grey-6 q-pa-none'").classes(
                                    "full-width q-mt-sm"
                                ):
                                    for grp, codes_in_grp in grouped_existing.items():
                                        if grp:
                                            ui.label(grp.upper()).style(
                                                "font-size: 12px; color: #757575;"
                                            ).classes("text-weight-medium q-mt-xs")
                                        indent = "padding-left: 24px;" if grp and has_groups else ""
                                        for p in codes_in_grp:
                                            selected[p["name"]] = False
                                            with ui.row().classes("items-center full-width no-wrap").style(indent):
                                                ui.element("div").style(
                                                    f"background: {p['colour']}; width: 14px; height: 14px; "
                                                    "border-radius: 50%; flex-shrink: 0;"
                                                )
                                                ui.label(p["name"]).classes("text-grey-5")

                        with ui.row().classes("q-mt-md justify-end full-width gap-2"):
                            ui.button("Cancel", on_click=import_dialog.close).props("flat")
                            new_count = len(new_codes)
                            btn_label = f"Import All {new_count}" if new_count > 0 else "Import 0"
                            import_btn = ui.button(
                                btn_label,
                                on_click=lambda: _do_import(preview, selected),
                            ).props("unelevated color=primary")
                            if new_count == 0:
                                import_btn.props("disable")

                    def _update_btn():
                        count = sum(selected.values())
                        new_total = len(new_codes)
                        if count == new_total and new_total > 0:
                            import_btn.set_text(f"Import All {count}")
                        else:
                            import_btn.set_text(f"Import {count}")
                        if count == 0:
                            import_btn.props("disable")
                        else:
                            import_btn.props(remove="disable")

                    def _update_toggle_link():
                        if all(selected.get(p["name"]) for p in new_codes):
                            toggle_link.set_text("none")
                        else:
                            toggle_link.set_text("all")

                    def _toggle(name, value, grp=""):
                        selected[name] = value
                        _update_btn()
                        _update_group_checkbox(grp)
                        _update_toggle_link()

                    def _toggle_all(value):
                        for p in new_codes:
                            selected[p["name"]] = value
                            if p["name"] in checkboxes:
                                checkboxes[p["name"]].value = value
                        # Update all group checkboxes
                        for grp in group_checkboxes:
                            gcb = group_checkboxes[grp]
                            gcb.props(remove="indeterminate")
                            gcb.value = value
                        toggle_link.set_text("all" if not value else "none")
                        _update_btn()

                    import_dialog.open()

                def _do_import(preview, selected):
                    to_import = [
                        {"name": p["name"], "colour": p["colour"], "group_name": p.get("group_name")}
                        for p in preview if selected.get(p["name"])
                    ]
                    try:
                        count = import_selected_codes(conn, to_import)
                    except Exception as exc:
                        ui.notify(f"Import failed: {exc}", type="negative", position="bottom")
                        return
                    import_dialog.close()
                    _refresh_codes()
                    code_list.refresh()
                    render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)
                    ui.notify(f"Imported {count} code(s).", type="positive", position="bottom")

                upload_el = ui.upload(on_upload=_handle_upload, auto_upload=True).props(
                    'accept=".csv" max-files=1'
                ).classes("hidden")

            # ── Inline code creation ─────────────────────────────────
            new_code_input = ui.input(placeholder="+ New code...").props(
                "dense outlined"
            ).classes("full-width q-mb-sm").style("flex-shrink: 0;")

            def _on_new_code_enter(e):
                name = new_code_input.value.strip()
                if not name:
                    return
                colour = next_colour(len(codes))
                add_code(conn, name, colour)
                new_code_input.value = ""
                _refresh_codes()
                code_list.refresh()
                render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)

            new_code_input.on("keydown.enter", _on_new_code_enter)

            # ── Code list (refreshable) ──────────────────────────────
            def _shortcut_label(i: int) -> str:
                if i < 9:
                    return str(i + 1)
                if i == 9:
                    return "0"
                if i < 36:
                    return chr(ord("a") + i - 10)
                return ""

            def _move_to_group(code, group_name):
                old_group = code["group_name"]
                move_dialog.close()
                update_code(conn, code["id"], group_name=group_name if group_name else "")
                _refresh_codes()
                code_list.refresh()
                render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)
                if old_group and not any(c["group_name"] == old_group for c in codes):
                    ui.notify(f"'{old_group}' group removed (no remaining codes).", type="info", position="bottom")

            def _open_new_group(code):
                move_dialog.close()
                def _on_create(name):
                    _move_to_group(code, name)
                open_new_group_dialog(new_group_dialog, _on_create)

            def _show_move_to_group(code):
                move_dialog.clear()
                existing_groups = sorted({c["group_name"] for c in codes if c["group_name"]})

                with move_dialog, ui.card().classes("q-pa-md").style("min-width: 250px;"):
                    ui.label("Move to Group").classes("text-subtitle1 text-weight-medium q-mb-sm")

                    for g in existing_groups:
                        with ui.row().classes("items-center full-width cursor-pointer q-py-xs").on(
                            "click", lambda _e, grp=g: _move_to_group(code, grp)
                        ):
                            if code["group_name"] == g:
                                ui.icon("check", size="xs").classes("text-grey-7")
                            else:
                                ui.element("div").style("width: 18px;")
                            ui.label(g).classes("text-body2")

                    if existing_groups:
                        ui.separator().classes("q-my-xs")

                    with ui.row().classes("items-center full-width cursor-pointer q-py-xs").on(
                        "click", lambda _e: _open_new_group(code)
                    ):
                        ui.icon("add", size="xs").classes("text-grey-7")
                        ui.label("New Group...").classes("text-body2")

                    with ui.row().classes("items-center full-width cursor-pointer q-py-xs").on(
                        "click", lambda _e: _move_to_group(code, None)
                    ):
                        if code["group_name"] is None:
                            ui.icon("check", size="xs").classes("text-grey-7")
                        else:
                            ui.element("div").style("width: 18px;")
                        ui.label("Ungrouped").classes("text-body2")

                move_dialog.open()

            def _render_code_row(code, shortcut: str, sorting: bool, pad_left: str = "2px 4px"):
                colour = code["colour"] or "#999999"

                async def _click_apply(_e, c=code):
                    await _apply_code(c)

                with ui.row().classes(
                    "items-center full-width no-wrap ace-hover-row ace-code-row"
                ).style(
                    f"gap: 4px; padding: {pad_left}; flex-shrink: 0; overflow: hidden;"
                    f" border-left: 4px solid {colour};"
                ) as row:
                    row.props(f'data-code-id={code["id"]}')
                    if not sorting:
                        ui.icon("drag_indicator", size="xs").classes(
                            "ace-drag-handle text-grey-5"
                        )
                    lbl = ui.label(code["name"]).classes(
                        "text-body2 col cursor-pointer ellipsis"
                    ).style(
                        "min-width: 0; line-height: 1.4;"
                    ).on("click", _click_apply)
                    with lbl:
                        ui.tooltip(code["name"]).props(":delay=1000")
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

            @ui.refreshable
            def code_list():
                sorting = state.get("sort_codes", False)
                if not codes:
                    with ui.row().classes("q-mt-sm").style("flex-wrap: wrap; gap: 0 4px;"):
                        ui.label("No codes yet. Type above to add one, or").classes("text-caption text-grey-6")
                        ui.link("import from CSV.", target="").classes("text-caption").on(
                            "click", lambda: _import_codes(), []
                        )
                    return

                has_groups = any(c["group_name"] for c in codes)

                if not has_groups:
                    # Flat list — unchanged behaviour
                    with ui.element("div").classes("full-width ace-code-list").style("flex-shrink: 0;"):
                        for i, code in enumerate(codes):
                            _render_code_row(code, _shortcut_label(i), sorting)
                    return

                # ── Grouped rendering ──────────────────────────────
                project_path = app.storage.general.get("project_path", "")
                collapse_key = f"collapsed_groups:{project_path}"
                collapsed = set(app.storage.general.get(collapse_key, []))

                # Build ordered groups: grouped first (order of first appearance), ungrouped last
                groups: dict[str | None, list] = {}
                group_order: list[str | None] = []
                for code in codes:
                    gn = code["group_name"] or None
                    if gn not in groups:
                        groups[gn] = []
                        group_order.append(gn)
                    groups[gn].append(code)

                grouped_items = [(k, groups[k]) for k in group_order if k is not None]
                ungrouped = groups.get(None, [])

                # Reorder codes list to match display order (grouped first, ungrouped last)
                # so that codes[i] matches shortcut_label(i)
                display_order = []
                for _, group_codes in grouped_items:
                    display_order.extend(group_codes)
                display_order.extend(ungrouped)
                codes.clear()
                codes.extend(display_order)
                codes_by_id.clear()
                codes_by_id.update({c["id"]: c for c in codes})

                def _toggle_group(group_name: str):
                    current = set(app.storage.general.get(collapse_key, []))
                    if group_name in current:
                        current.discard(group_name)
                    else:
                        current.add(group_name)
                    app.storage.general[collapse_key] = list(current)
                    code_list.refresh()

                global_idx = 0
                for group_name, group_codes in grouped_items:
                    is_collapsed = group_name in collapsed

                    # Shortcut range for collapsed header label
                    first_sc = _shortcut_label(global_idx)
                    last_sc = _shortcut_label(global_idx + len(group_codes) - 1)
                    range_str = ""
                    if first_sc and last_sc and first_sc != last_sc:
                        range_str = f" [{first_sc}\u2013{last_sc}]"
                    elif first_sc:
                        range_str = f" [{first_sc}]"

                    header_classes = "ace-group-header"
                    if is_collapsed:
                        header_classes += " collapsed"

                    with ui.element("div").classes(header_classes).on(
                        "click", lambda _e, gn=group_name: _toggle_group(gn)
                    ):
                        icon_name = "chevron_right" if is_collapsed else "expand_more"
                        ui.icon(icon_name, size="xs").classes("chevron")
                        label_text = group_name
                        if is_collapsed:
                            label_text += range_str
                        ui.label(label_text)

                    visible = not is_collapsed
                    with ui.element("div").classes(
                        "full-width ace-code-list"
                    ).style("flex-shrink: 0;") as code_div:
                        for code in group_codes:
                            _render_code_row(code, _shortcut_label(global_idx), sorting, pad_left="2px 4px 2px 20px")
                            global_idx += 1
                    code_div.set_visibility(visible)

                # Ungrouped codes at the bottom (no header, no collapse)
                if ungrouped:
                    with ui.element("div").classes("full-width ace-code-list").style("flex-shrink: 0;"):
                        for code in ungrouped:
                            _render_code_row(code, _shortcut_label(global_idx), sorting)
                            global_idx += 1

            code_list()

        # ── Right Panel (flex) ───────────────────────────────────────
        with splitter.after:
          with ui.column().classes("q-pa-md").style("width: 100%; overflow-y: auto;"):

            # Source header
            @ui.refreshable
            def source_header():
                asn = current_assignment()
                src = get_source(conn, asn["source_id"])
                with ui.row().classes("items-center full-width q-mb-sm"):
                    ui.label(src["display_id"]).classes("text-h6 text-weight-medium")
                    status = asn["status"]
                    icon_name, icon_colour = _STATUS_ICONS.get(status, ("help", "grey"))
                    ui.icon(icon_name).style(
                        f"color: {icon_colour}; font-size: 1.2rem;"
                    ).tooltip(status.replace("_", " ").title())
                    ui.space()
                    is_flagged = asn["status"] == "flagged"
                    ui.button(
                        icon="flag",
                        on_click=lambda: _toggle_flag(),
                    ).props(
                        f"{'unelevated color=negative' if is_flagged else 'flat color=grey-5'} round dense size=sm"
                    ).tooltip("Flagged" if is_flagged else "Flag this source")

                if src["metadata_json"]:
                    try:
                        meta = json.loads(src["metadata_json"])
                        with ui.row().classes("q-mb-sm gap-2"):
                            for k, v in meta.items():
                                ui.label(f"{k}: {v}").classes(
                                    "text-caption text-grey-7 bg-grey-2 q-px-xs"
                                )
                    except (json.JSONDecodeError, TypeError):
                        pass

            source_header()

            # Text content area
            ui.label("Source").classes("text-subtitle2 text-weight-medium q-mt-sm")
            text_container = ui.html("", sanitize=False).classes("full-width ace-text-content")

            ui.separator().classes("q-my-sm")

            # Annotation list
            ui.label("Annotations").classes("text-subtitle2 text-weight-medium q-mt-sm")

            @ui.refreshable
            def annotation_list_display():
                anns = get_annotations_for_source(conn, current_source_id(), coder_id)
                if not anns:
                    ui.label("No annotations yet.").classes("text-caption text-grey-6")
                else:
                    with ui.column().classes("full-width gap-0 ace-no-scrollbar").style(
                        "max-height: 150px; overflow-y: auto;"
                    ):
                        for ann in anns:
                            code = codes_by_id.get(ann["code_id"])
                            colour = code["colour"] if code else "#999999"
                            code_name = code["name"] if code else "Unknown"
                            selected = ann["selected_text"] or ""
                            ann_id = ann["id"]
                            with ui.row().classes(
                                "items-center full-width ace-hover-row cursor-pointer"
                            ).style(
                                f"gap: 6px; padding: 2px 6px; min-height: 0;"
                                f" border-left: 3px solid {colour};"
                            ).on(
                                "click",
                                lambda _e, aid=ann_id: ui.run_javascript(
                                    f'aceFlashAnnotation("{aid}")'
                                ),
                            ):
                                ui.label(code_name).classes(
                                    "text-caption text-weight-medium"
                                ).style("flex-shrink: 0;")
                                ui.label(f'"{selected}"').classes(
                                    "text-caption text-grey-6 ellipsis"
                                ).style("min-width: 0; flex: 1;")
                                ui.button(
                                    icon="close",
                                    on_click=lambda _e, a=ann: _delete_annotation(a),
                                ).props("flat round dense size=xs color=grey-5").classes("ace-hover-action")

            annotation_list_display()


    # ── Source Grid Navigator + Bottom Bar ──────────────────────────
    grid_container, bottom_bar, _toggle_grid = build_bottom_bar(
        conn=conn,
        coder_id=coder_id,
        assignments=assignments,
        state=state,
        sources=sources,
        navigate_to_fn=lambda idx: _navigate_to(idx),
    )

    # ── Helpers ────────────────────────────────────────────────────────

    def _refresh_all():
        _refresh_codes()
        code_list.refresh()
        render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)
        annotation_list_display.refresh()

    # ── Apply code (no dialog) ───────────────────────────────────────

    async def _apply_code(code):
        await apply_code(state, conn, coder_id, current_source_id, codes_by_id, text_container, annotation_list_display.refresh, undo_mgr, code)

    # ── Delete annotation ────────────────────────────────────────────

    def _delete_annotation(ann, dialog=None):
        delete_annotation_action(conn, ann, undo_mgr, codes_by_id, coder_id, text_container, annotation_list_display.refresh, dialog)

    # ── Navigation ───────────────────────────────────────────────────

    def _navigate_to(idx):
        navigate_to(conn, coder_id, state, assignments, codes_by_id, text_container, source_header.refresh, bottom_bar.refresh, annotation_list_display.refresh, _reload_assignments, idx)

    # ── Status toggles ───────────────────────────────────────────────

    def _toggle_flag():
        toggle_flag(conn, coder_id, state, assignments, source_header.refresh, bottom_bar.refresh, _reload_assignments)

    # ── Event handlers & keyboard shortcuts ───────────────────────────
    register_shortcuts(
        state=state,
        conn=conn,
        coder_id=coder_id,
        codes=codes,
        codes_by_id=codes_by_id,
        undo_mgr=undo_mgr,
        text_container=text_container,
        annotation_list_refresh=annotation_list_display.refresh,
        grid_container=grid_container,
        annotation_info_dialog=annotation_info_dialog,
        assignments=assignments,
        current_source_id=current_source_id,
        navigate_to_fn=_navigate_to,
        toggle_grid_fn=_toggle_grid,
        refresh_codes_fn=_refresh_codes,
        code_list_refresh=code_list.refresh,
        delete_annotation_fn=_delete_annotation,
    )

    # ── Initial render ───────────────────────────────────────────────
    render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)
    auto_transition(conn, coder_id, state, assignments, _reload_assignments)


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register() -> None:
    @ui.page("/code")
    def code_page():
        project_path = app.storage.general.get("project_path")
        if not project_path:
            ui.navigate.to("/")
            return
        try:
            conn = open_project(project_path)
        except (ValueError, FileNotFoundError) as exc:
            ui.notify(str(exc), type="negative")
            ui.navigate.to("/")
            return

        def _cleanup():
            try:
                checkpoint_and_close(conn)
            except Exception:
                pass

        ui.context.client.on_disconnect(_cleanup)
        build(conn)
