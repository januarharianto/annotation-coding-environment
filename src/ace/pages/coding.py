"""New two-pane coding interface with inline code creation."""

import hashlib
import html
import json
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from nicegui import app, events, ui

from ace.db.connection import checkpoint_and_close, open_project
from ace.models.annotation import (
    get_annotation_counts_by_source,
    get_annotations_for_source,
)
from ace.models.assignment import get_assignments_for_coder
from ace.models.codebook import add_code, export_codebook_to_csv, import_codebook_from_csv, list_codes
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
from ace.pages.coding_dialogs import open_colour_dialog, open_delete_dialog, open_rename_dialog
from ace.pages.coding_shortcuts import register_shortcuts
from ace.services.palette import next_colour
from ace.services.undo import UndoManager

_STATIC_DIR = Path(__file__).parent.parent / "static"
_BRIDGE_HASH = hashlib.md5((_STATIC_DIR / "js" / "bridge.js").read_bytes()).hexdigest()[:8]
_CSS_HASH = hashlib.md5((_STATIC_DIR / "css" / "annotator.css").read_bytes()).hexdigest()[:8]
_SORTABLE_HASH = hashlib.md5((_STATIC_DIR / "js" / "Sortable.min.js").read_bytes()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Annotation rendering
# ---------------------------------------------------------------------------

def _annotation_span(data: dict) -> str:
    hex_c = data["colour"].lstrip("#")
    if len(hex_c) == 6:
        r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    else:
        r, g, b = 153, 153, 153
    return (
        f'<span class="ace-annotation" '
        f'data-annotation-id="{html.escape(data["id"])}" '
        f'title="{html.escape(data["code_name"])}" '
        f'aria-label="{html.escape(data["code_name"])}" '
        f'style="background-color: rgba({r},{g},{b},0.3);">'
    )


def render_annotated_text(text: str, annotations: list, codes_by_id: dict) -> str:
    if not text:
        return ""

    events_list: list[tuple[int, int, str, dict | None]] = []
    for ann in annotations:
        start = ann["start_offset"]
        end = ann["end_offset"]
        code = codes_by_id.get(ann["code_id"])
        colour = code["colour"] if code else "#999999"
        code_name = code["name"] if code else "Unknown"
        events_list.append((start, 0, "open", {
            "id": ann["id"],
            "colour": colour,
            "code_name": code_name,
        }))
        events_list.append((end, 1, "close", {"id": ann["id"]}))

    events_list.sort(key=lambda e: (e[0], e[1]))

    parts: list[str] = []
    pos = 0
    open_stack: list[dict] = []

    for offset, kind_order, kind, data in events_list:
        if offset > pos:
            parts.append(html.escape(text[pos:offset]))
            pos = offset

        if kind == "open":
            parts.append(_annotation_span(data))
            open_stack.append(data)
        else:
            target_id = data["id"]
            idx = None
            for i in range(len(open_stack) - 1, -1, -1):
                if open_stack[i]["id"] == target_id:
                    idx = i
                    break
            if idx is not None:
                to_reopen = []
                for i in range(len(open_stack) - 1, idx, -1):
                    parts.append("</span>")
                    to_reopen.append(open_stack[i])
                parts.append("</span>")
                open_stack.pop(idx)
                for item in reversed(to_reopen):
                    parts.append(_annotation_span(item))

    if pos < len(text):
        parts.append(html.escape(text[pos:]))

    for _ in open_stack:
        parts.append("</span>")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Status icon helper
# ---------------------------------------------------------------------------

_STATUS_ICONS = {
    "pending": ("radio_button_unchecked", "#757575"),
    "in_progress": ("edit", "#1565c0"),
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
        'html, body { overflow: hidden; height: 100vh; } '
        '.q-page { display: flex; flex-direction: column; height: 100%; } '
        '.q-page > .nicegui-content { flex: 1; min-height: 0; display: flex; flex-direction: column; }'
        '</style>'
    )

    annotation_info_dialog = ui.dialog()
    rename_dialog = ui.dialog()
    colour_dialog = ui.dialog()
    delete_dialog = ui.dialog()

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
                        ui.menu_item("Import CSV...", on_click=lambda: _import_codes()).props(
                            "disable" if codes else ""
                        )
                        ui.menu_item("Export CSV", on_click=lambda: _export_codes()).props(
                            "disable" if not codes else ""
                        )

                def _handle_upload(e: events.UploadEventArguments):
                    try:
                        content = e.content.read().decode("utf-8-sig")
                        tmp = tempfile.NamedTemporaryFile(
                            suffix=".csv", delete=False, prefix="ace_import_", mode="w", encoding="utf-8",
                        )
                        tmp.write(content)
                        tmp.close()
                        count = import_codebook_from_csv(conn, tmp.name)
                        Path(tmp.name).unlink(missing_ok=True)
                        _refresh_codes()
                        code_list.refresh()
                        render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)
                        ui.notify(f"Imported {count} code(s).", type="positive", position="bottom")
                    except Exception as exc:
                        ui.notify(f"Import failed: {exc}", type="negative", position="bottom")

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
                with ui.element("div").classes("full-width ace-code-list").style("flex-shrink: 0;"):
                    for i, code in enumerate(codes):
                        if i < 9:
                            shortcut = str(i + 1)
                        elif i == 9:
                            shortcut = "0"
                        elif i < 36:
                            shortcut = chr(ord("a") + i - 10)
                        else:
                            shortcut = ""
                        colour = code["colour"] or "#999999"

                        async def _click_apply(_e, c=code):
                            await _apply_code(c)

                        with ui.row().classes(
                            "items-center full-width no-wrap ace-hover-row ace-code-row"
                        ).style(
                            f"gap: 4px; padding: 2px 4px; flex-shrink: 0; overflow: hidden;"
                            f" border-left: 4px solid {colour};"
                        ) as row:
                            row.props(f'data-code-id={code["id"]}')
                            # Drag handle (hidden when sorting by name)
                            if not sorting:
                                ui.icon("drag_indicator", size="xs").classes(
                                    "ace-drag-handle text-grey-5"
                                )
                            # Name (clickable to apply code)
                            lbl = ui.label(code["name"]).classes(
                                "text-body2 col cursor-pointer ellipsis"
                            ).style(
                                "min-width: 0; line-height: 1.4;"
                            ).on("click", _click_apply)
                            with lbl:
                                ui.tooltip(code["name"]).props(":delay=1000")
                            if shortcut:
                                ui.label(shortcut).classes("ace-keycap")
                            # "..." menu (visible on hover)
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
                                    ui.menu_item(
                                        "Delete",
                                        on_click=lambda _e, c=code: open_delete_dialog(conn, delete_dialog, c, _refresh_all),
                                    )

            code_list()

        # ── Right Panel (flex) ───────────────────────────────────────
        with splitter.after:
          with ui.column().classes("col q-pa-md").style("overflow-y: auto;"):

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


    # ── Source Grid Navigator ────────────────────────────────────────

    grid_container = ui.column().classes("full-width").style(
        "border-top: 1px solid #bdbdbd; background: #f5f5f5;"
    )
    grid_container.set_visibility(False)

    sources_by_id = {s["id"]: s for s in sources}

    def _build_grid_html():
        counts = get_annotation_counts_by_source(conn, coder_id)
        max_count = max(counts.values()) if counts else 1
        total = len(assignments)
        cell_size = max(10, min(24, int((700 * 200 / max(total, 1)) ** 0.5)))
        cells = []
        for i, asn in enumerate(assignments):
            sid = asn["source_id"]
            count = counts.get(sid, 0)
            is_current = i == state["current_index"]
            is_flagged = asn["status"] == "flagged"
            if is_current:
                bg = "#222"
            else:
                lightness = 95 - int(65 * count / max_count) if max_count else 95
                bg = f"hsl(210, 70%, {lightness}%)"
            border = "2px solid #d84315" if is_flagged else ("2px solid white" if is_current else "1px solid #bdbdbd")
            src = sources_by_id.get(sid)
            display_id = src["display_id"] if src else f"Source {i + 1}"
            safe_title = html.escape(f"{display_id} ({count} annotations)", quote=True)
            cells.append(
                f'<span class="ace-grid-cell" data-idx="{i}" '
                f'title="{safe_title}" '
                f'style="width:{cell_size}px;height:{cell_size}px;background:{bg};'
                f'border:{border};display:inline-block;"></span>'
            )
        legend = (
            '<div class="ace-grid-legend">'
            f'<span><span style="display:inline-block;width:10px;height:10px;background:hsl(210,70%,95%);border:1px solid #ccc;"></span> 0</span>'
            f'<span><span style="display:inline-block;width:10px;height:10px;background:hsl(210,70%,60%);border:1px solid #ccc;"></span> some</span>'
            f'<span><span style="display:inline-block;width:10px;height:10px;background:hsl(210,70%,30%);border:1px solid #ccc;"></span> most</span>'
            f'<span><span style="display:inline-block;width:10px;height:10px;background:#222;border:2px solid white;"></span> current</span>'
            f'<span><span style="display:inline-block;width:10px;height:10px;background:hsl(210,70%,80%);border:2px solid #d84315;"></span> flagged</span>'
            '</div>'
        )
        return legend + '<div class="ace-source-grid">' + "".join(cells) + "</div>"

    grid_html = ui.html("", sanitize=False)
    grid_html.move(grid_container)

    def _toggle_grid():
        visible = grid_container.visible
        if not visible:
            grid_html.content = _build_grid_html()
        grid_container.set_visibility(not visible)

    def _on_grid_cell_clicked(e):
        idx = e.args.get("index")
        if idx is not None and 0 <= idx < len(assignments):
            grid_container.set_visibility(False)
            _navigate_to(idx)

    ui.on("grid_cell_clicked", _on_grid_cell_clicked)

    # ── Bottom Bar ────────────────────────────────────────────────────
    @ui.refreshable
    def bottom_bar():
        total = len(assignments)
        complete_count = sum(1 for a in assignments if a["status"] == "complete")
        pct = round(complete_count / total * 100) if total else 0
        idx = state["current_index"]

        with ui.row().classes(
            "items-center full-width q-pa-sm justify-between"
        ).style(
            "border-top: 1px solid #bdbdbd; background: #f5f5f5;"
        ):
            # Nav buttons
            with ui.row().classes("items-center gap-2"):
                ui.button(
                    "Prev",
                    icon="chevron_left",
                    on_click=lambda: _navigate_to(max(0, idx - 1)),
                ).props("flat dense" + (" disable" if idx == 0 else "")).tooltip("Alt+\u2190")

                ui.button(
                    f"Source {idx + 1} of {total} ({pct}% complete) \u25BE",
                    on_click=_toggle_grid,
                ).props("flat dense no-caps").classes("text-body2 text-grey-8").tooltip("G")

                ui.button(
                    "Next",
                    icon="chevron_right",
                    on_click=lambda: _navigate_to(min(total - 1, idx + 1)),
                ).props("flat dense" + (" disable" if idx >= total - 1 else "")).tooltip("Alt+\u2192")

    bottom_bar()

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
