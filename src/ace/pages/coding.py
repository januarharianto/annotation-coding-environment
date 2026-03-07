"""New two-pane coding interface with inline code creation."""

import hashlib
import html
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from nicegui import app, events, ui

from ace.db.connection import checkpoint_and_close, open_project
from ace.models.annotation import (
    add_annotation,
    delete_annotation,
    get_annotations_for_source,
    undelete_annotation,
)
from ace.models.assignment import get_assignments_for_coder, update_assignment_status
from ace.models.codebook import add_code, delete_code, list_codes, update_code
from ace.models.coder import add_coder, list_coders
from ace.models.project import get_project
from ace.models.source import get_source, get_source_content, list_sources
from ace.services.offset import utf16_to_codepoint
from ace.services.palette import COLOUR_PALETTE, next_colour
from ace.services.undo import UndoManager

_STATIC_DIR = Path(__file__).parent.parent / "static"
_BRIDGE_HASH = hashlib.md5((_STATIC_DIR / "js" / "bridge.js").read_bytes()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Source note helpers
# ---------------------------------------------------------------------------

def _get_note(conn: sqlite3.Connection, source_id: str, coder_id: str) -> str:
    row = conn.execute(
        "SELECT note_text FROM source_note WHERE source_id = ? AND coder_id = ?",
        (source_id, coder_id),
    ).fetchone()
    return row["note_text"] if row else ""


def _upsert_note(
    conn: sqlite3.Connection, source_id: str, coder_id: str, text: str
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    existing = conn.execute(
        "SELECT id FROM source_note WHERE source_id = ? AND coder_id = ?",
        (source_id, coder_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE source_note SET note_text = ?, updated_at = ? "
            "WHERE source_id = ? AND coder_id = ?",
            (text, now, source_id, coder_id),
        )
    else:
        note_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO source_note (id, source_id, coder_id, note_text, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, source_id, coder_id, text, now, now),
        )
    conn.commit()


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
        code_name = code["name"] if code else "?"
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
    "pending": ("radio_button_unchecked", "grey"),
    "in_progress": ("timelapse", "orange"),
    "complete": ("check_circle", "green"),
    "flagged": ("flag", "red"),
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
    coders = list_coders(conn)
    if not coders:
        coder_id = add_coder(conn, "default")
    else:
        coder_id = coders[0]["id"]

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

    def _auto_transition():
        asn = current_assignment()
        if asn["status"] == "pending":
            update_assignment_status(conn, asn["source_id"], coder_id, "in_progress")
            _reload_assignments()

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
    ui.add_head_html('<link rel="stylesheet" href="/static/css/annotator.css">')
    ui.add_head_html(f'<script src="/static/js/bridge.js?v={_BRIDGE_HASH}" defer></script>')
    ui.add_head_html(
        '<style>'
        'html, body { overflow: hidden; height: 100vh; } '
        '.q-page { display: flex; flex-direction: column; height: 100vh; } '
        '.q-page > .nicegui-content { flex: 1; min-height: 0; display: flex; flex-direction: column; }'
        '</style>'
    )

    annotation_info_dialog = ui.dialog()

    # ── Main two-pane container ──────────────────────────────────────
    with ui.row().classes("full-width no-wrap col").style(
        "overflow: hidden;"
    ):

        # ── Left Panel (280px) ───────────────────────────────────────
        with ui.column().classes("q-pa-md").style(
            "width: 280px; min-width: 280px; overflow-y: auto; "
            "border-right: 1px solid #e0e0e0;"
        ):
            # Back button
            ui.button(icon="arrow_back", on_click=lambda: _go_home(conn)).props(
                "flat round dense"
            ).tooltip("Back to home")

            ui.label("Codes").classes(
                "text-subtitle1 text-weight-medium q-mt-sm"
            )

            # ── Inline code creation ─────────────────────────────────
            new_code_input = ui.input(placeholder="+ New code...").props(
                "dense outlined"
            ).classes("full-width q-mb-sm")

            def _on_new_code_enter(e):
                name = new_code_input.value.strip()
                if not name:
                    return
                colour = next_colour(len(codes))
                add_code(conn, name, colour)
                new_code_input.value = ""
                _refresh_codes()
                code_list.refresh()
                _render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)

            new_code_input.on("keydown.enter", _on_new_code_enter)

            # ── Code list (refreshable) ──────────────────────────────
            @ui.refreshable
            def code_list():
                for i, code in enumerate(codes):
                    shortcut = str(i + 1) if i < 9 else ""
                    colour = code["colour"] or "#999999"
                    with ui.row().classes(
                        "items-center q-py-xs full-width"
                    ).style("gap: 8px;"):
                        # Colour dot + name (clickable to apply code)
                        async def _click_apply(_e, c=code):
                            await _apply_code(c)

                        with ui.row().classes(
                            "items-center col cursor-pointer"
                        ).style("gap: 8px; min-width: 0;").on(
                            "click", _click_apply,
                        ):
                            ui.element("div").classes("ace-code-dot").style(
                                f"background-color: {colour};"
                            )
                            lbl = ui.label(code["name"]).classes(
                                "text-body2"
                            ).style("min-width: 0; word-break: break-word;")
                            if code["description"]:
                                lbl.tooltip(code["description"])
                        if shortcut:
                            ui.label(shortcut).classes(
                                "text-caption text-grey-5"
                            ).style(
                                "background: #eee; padding: 0 5px; font-family: monospace;"
                            )
                        # "..." menu
                        with ui.button(icon="more_horiz").props(
                            "flat round dense size=sm"
                        ):
                            with ui.menu():
                                ui.menu_item(
                                    "Rename",
                                    on_click=lambda _e, c=code: _open_rename_dialog(c),
                                )
                                ui.menu_item(
                                    "Change colour",
                                    on_click=lambda _e, c=code: _open_colour_dialog(c),
                                )
                                ui.menu_item(
                                    "Delete",
                                    on_click=lambda _e, c=code: _open_delete_dialog(c),
                                )

            code_list()

        # ── Right Panel (flex) ───────────────────────────────────────
        with ui.column().classes("col q-pa-md").style("overflow-y: auto;"):

            # Source header
            @ui.refreshable
            def source_header():
                asn = current_assignment()
                src = get_source(conn, asn["source_id"])
                with ui.row().classes("items-center q-mb-sm"):
                    ui.label(src["display_id"]).classes("text-h6 text-weight-medium")
                    status = asn["status"]
                    icon_name, icon_colour = _STATUS_ICONS.get(status, ("help", "grey"))
                    ui.icon(icon_name).style(
                        f"color: {icon_colour}; font-size: 1.2rem;"
                    ).tooltip(status.replace("_", " ").title())

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
                    ui.label("No annotations yet.").classes("text-body2 text-grey-6")
                else:
                    for ann in anns:
                        code = codes_by_id.get(ann["code_id"])
                        colour = code["colour"] if code else "#999999"
                        code_name = code["name"] if code else "Unknown"
                        with ui.row().classes("items-center q-py-xs full-width").style("gap: 8px;"):
                            ui.element("div").classes("ace-code-dot").style(
                                f"background-color: {colour};"
                            )
                            selected = ann["selected_text"] or ""
                            truncated = selected[:60] + ("..." if len(selected) > 60 else "")
                            with ui.column().classes("col").style("min-width: 0;"):
                                ui.label(code_name).classes("text-caption text-weight-medium")
                                ui.label(f'"{truncated}"').classes(
                                    "text-caption text-grey-7 ellipsis"
                                )
                            ui.button(
                                icon="close",
                                on_click=lambda _e, a=ann: _delete_annotation(a),
                            ).props("flat round dense size=sm color=negative")

            annotation_list_display()

            ui.separator().classes("q-my-sm")

            # Notes field
            ui.label("Notes").classes("text-subtitle2 text-weight-medium")
            notes_area = ui.textarea(placeholder="Add notes for this source...").props(
                "outlined autogrow"
            ).classes("full-width")

            def _save_notes():
                _upsert_note(conn, current_source_id(), coder_id, notes_area.value or "")

            notes_area.on("blur", lambda _e: _save_notes())

    # ── Bottom Bar ────────────────────────────────────────────────────
    @ui.refreshable
    def bottom_bar():
        total = len(assignments)
        complete_count = sum(1 for a in assignments if a["status"] == "complete")
        pct = round(complete_count / total * 100) if total else 0
        idx = state["current_index"]
        asn = current_assignment()

        with ui.row().classes(
            "items-center full-width q-pa-sm justify-between"
        ).style(
            "border-top: 1px solid #e0e0e0; background: #fafafa;"
        ):
            # Nav buttons
            with ui.row().classes("items-center gap-2"):
                ui.button(
                    "Prev",
                    icon="chevron_left",
                    on_click=lambda: _navigate_to(max(0, idx - 1)),
                ).props("flat dense" + (" disable" if idx == 0 else ""))

                ui.label(
                    f"Source {idx + 1} of {total} ({pct}% complete)"
                ).classes("text-body2 text-grey-8")

                ui.button(
                    "Next",
                    icon="chevron_right",
                    on_click=lambda: _navigate_to(min(total - 1, idx + 1)),
                ).props("flat dense" + (" disable" if idx >= total - 1 else "")).classes("q-mr-md")

            # Status buttons
            with ui.row().classes("items-center gap-2"):
                is_complete = asn["status"] == "complete"
                ui.button(
                    "Completed" if is_complete else "Mark Complete",
                    icon="check_circle" if is_complete else "check_circle_outline",
                    on_click=lambda: _toggle_complete(),
                ).props(
                    f"{'unelevated color=positive' if is_complete else 'outline'} dense"
                )

                is_flagged = asn["status"] == "flagged"
                ui.button(
                    "Flagged" if is_flagged else "Flag",
                    icon="flag",
                    on_click=lambda: _toggle_flag(),
                ).props(
                    f"{'unelevated color=negative' if is_flagged else 'outline'} dense"
                )

    bottom_bar()

    # ── Code management dialogs ──────────────────────────────────────

    def _open_rename_dialog(code):
        with ui.dialog(value=True) as dlg, ui.card().classes("q-pa-md").style("min-width: 300px;"):
            ui.label("Rename Code").classes("text-subtitle1 text-weight-medium q-mb-sm")
            name_input = ui.input("Name", value=code["name"]).props("autofocus outlined dense")

            with ui.row().classes("q-mt-md justify-end full-width gap-2"):
                ui.button("Cancel", on_click=dlg.close).props("flat")

                def _save_rename():
                    new_name = name_input.value.strip()
                    if not new_name:
                        return
                    update_code(conn, code["id"], name=new_name)
                    dlg.close()
                    _refresh_codes()
                    code_list.refresh()
                    _render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)
                    annotation_list_display.refresh()

                ui.button("Save", on_click=_save_rename).props("unelevated color=primary")

    def _open_colour_dialog(code):
        with ui.dialog(value=True) as dlg, ui.card().classes("q-pa-md").style("min-width: 300px;"):
            ui.label("Change Colour").classes("text-subtitle1 text-weight-medium q-mb-sm")
            ui.label(code["name"]).classes("text-body2 text-grey-7 q-mb-sm")

            with ui.row().classes("gap-2").style("flex-wrap: wrap;"):
                for hex_colour, colour_name in COLOUR_PALETTE:
                    def _pick(c=hex_colour):
                        update_code(conn, code["id"], colour=c)
                        dlg.close()
                        _refresh_codes()
                        code_list.refresh()
                        _render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)
                        annotation_list_display.refresh()

                    is_current = (code["colour"] or "").lower() == hex_colour.lower()
                    ui.element("div").classes("ace-code-dot cursor-pointer").style(
                        f"background-color: {hex_colour}; width: 28px; height: 28px; "
                        f"border: {'3px solid #333' if is_current else '2px solid transparent'};"
                    ).tooltip(colour_name).on("click", _pick)

            with ui.row().classes("q-mt-md justify-end full-width"):
                ui.button("Cancel", on_click=dlg.close).props("flat")

    def _open_delete_dialog(code):
        with ui.dialog(value=True) as dlg, ui.card().classes("q-pa-md").style("min-width: 300px;"):
            ui.label("Delete Code").classes("text-subtitle1 text-weight-medium q-mb-sm")
            ui.label(
                f'Are you sure you want to delete "{code["name"]}"?'
            ).classes("text-body2 q-mb-sm")
            ui.label(
                "Existing annotations using this code will remain but show as 'Unknown'."
            ).classes("text-caption text-grey-7 q-mb-md")

            with ui.row().classes("justify-end full-width gap-2"):
                ui.button("Cancel", on_click=dlg.close).props("flat")

                def _confirm_delete():
                    delete_code(conn, code["id"])
                    dlg.close()
                    _refresh_codes()
                    code_list.refresh()
                    _render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)
                    annotation_list_display.refresh()

                ui.button("Delete", on_click=_confirm_delete).props(
                    "unelevated color=negative"
                )

    # ── Apply code (no dialog) ───────────────────────────────────────

    async def _apply_code(code):
        sel = state.get("pending_selection")
        if not sel:
            # Fallback: read snapshot captured on last mousedown
            sel = await ui.run_javascript("window.__aceLastSelection")
            if sel:
                state["pending_selection"] = sel
        if not sel:
            ui.notify("Select text first, then click a code.", type="info", position="bottom", timeout=2000)
            return

        source_id = current_source_id()
        content_row = get_source_content(conn, source_id)
        text = content_row["content_text"] if content_row else ""

        start_cp = utf16_to_codepoint(text, sel["start"])
        end_cp = utf16_to_codepoint(text, sel["end"])
        selected_text = text[start_cp:end_cp]

        ann_id = add_annotation(
            conn,
            source_id=source_id,
            coder_id=coder_id,
            code_id=code["id"],
            start_offset=start_cp,
            end_offset=end_cp,
            selected_text=selected_text,
        )
        undo_mgr.record_add(source_id, ann_id)

        state["pending_selection"] = None
        _render_text(conn, source_id, coder_id, codes_by_id, text_container)
        annotation_list_display.refresh()

    # ── Delete annotation ────────────────────────────────────────────

    def _delete_annotation(ann, dialog=None):
        source_id = ann["source_id"]
        undo_mgr.record_delete(source_id, ann["id"])
        delete_annotation(conn, ann["id"])
        if dialog:
            dialog.close()
        _render_text(conn, source_id, coder_id, codes_by_id, text_container)
        annotation_list_display.refresh()
        ui.notify("Annotation removed.", type="info", position="bottom", timeout=1500)

    # ── Annotation info dialog ───────────────────────────────────────

    def _open_annotation_info(ann_ids):
        anns = []
        for aid in ann_ids:
            row = conn.execute(
                "SELECT * FROM annotation WHERE id = ? AND deleted_at IS NULL", (aid,)
            ).fetchone()
            if row:
                anns.append(row)

        if not anns:
            return

        annotation_info_dialog.clear()
        with annotation_info_dialog, ui.card().classes("q-pa-sm").style("min-width: 250px;"):
            ui.label("Annotations").classes("text-subtitle2 text-weight-medium q-mb-xs")

            for ann in anns:
                code = codes_by_id.get(ann["code_id"])
                colour = code["colour"] if code else "#999999"
                code_name = code["name"] if code else "Unknown"
                selected = ann["selected_text"] or ""
                truncated = selected[:60] + ("..." if len(selected) > 60 else "")

                with ui.row().classes("items-center q-py-xs full-width").style("gap: 8px;"):
                    ui.element("div").classes("ace-code-dot").style(
                        f"background-color: {colour};"
                    )
                    with ui.column().classes("col").style("min-width: 0;"):
                        ui.label(code_name).classes("text-body2 text-weight-medium")
                        ui.label(f'"{truncated}"').classes("text-caption text-grey-7 ellipsis")
                    ui.button(
                        icon="delete",
                        on_click=lambda _e, a=ann: _delete_annotation(a, annotation_info_dialog),
                    ).props("flat round dense size=sm color=negative")

            ui.button("Close", on_click=annotation_info_dialog.close).props("flat dense").classes("q-mt-xs")

        annotation_info_dialog.open()

    # ── Navigation ───────────────────────────────────────────────────

    def _navigate_to(idx):
        if idx == state["current_index"]:
            return

        state["current_index"] = idx
        state["pending_selection"] = None

        asn = assignments[idx]
        source_id = asn["source_id"]

        if asn["status"] == "pending":
            update_assignment_status(conn, source_id, coder_id, "in_progress")
            _reload_assignments()

        _render_text(conn, source_id, coder_id, codes_by_id, text_container)
        _load_notes(conn, source_id, coder_id, notes_area)
        source_header.refresh()
        bottom_bar.refresh()
        annotation_list_display.refresh()

    # ── Status toggles ───────────────────────────────────────────────

    def _toggle_complete():
        asn = current_assignment()
        new_status = "in_progress" if asn["status"] == "complete" else "complete"
        update_assignment_status(conn, asn["source_id"], coder_id, new_status)
        _reload_assignments()
        source_header.refresh()
        bottom_bar.refresh()

    def _toggle_flag():
        asn = current_assignment()
        new_status = "in_progress" if asn["status"] == "flagged" else "flagged"
        update_assignment_status(conn, asn["source_id"], coder_id, new_status)
        _reload_assignments()
        source_header.refresh()
        bottom_bar.refresh()

    # ── Event handlers from JS ───────────────────────────────────────

    def _on_text_selected(e):
        data = e.args
        state["pending_selection"] = {
            "start": data["start"],
            "end": data["end"],
            "text": data["text"],
        }

    def _on_annotation_clicked(e):
        data = e.args
        ann_ids = data.get("annotation_ids", [])
        if ann_ids:
            _open_annotation_info(ann_ids)

    ui.on("text_selected", _on_text_selected)
    ui.on("annotation_clicked", _on_annotation_clicked)

    # ── Keyboard shortcut handlers ───────────────────────────────────

    def _on_shortcut_undo(_e):
        _do_undo(conn, coder_id, codes_by_id, text_container, annotation_list_display, undo_mgr, current_source_id())

    def _on_shortcut_redo(_e):
        _do_redo(conn, coder_id, codes_by_id, text_container, annotation_list_display, undo_mgr, current_source_id())

    def _on_shortcut_mark_complete(_e):
        _toggle_complete()

    def _on_shortcut_escape(_e):
        state["pending_selection"] = None
        annotation_info_dialog.close()

    def _on_shortcut_prev(_e):
        idx = state["current_index"]
        if idx > 0:
            _navigate_to(idx - 1)

    def _on_shortcut_next(_e):
        idx = state["current_index"]
        if idx < len(assignments) - 1:
            _navigate_to(idx + 1)

    async def _on_shortcut_apply_code(e):
        code_idx = e.args.get("index", -1)
        if 0 <= code_idx < len(codes):
            await _apply_code(codes[code_idx])

    ui.on("shortcut_undo", _on_shortcut_undo)
    ui.on("shortcut_redo", _on_shortcut_redo)
    ui.on("shortcut_mark_complete", _on_shortcut_mark_complete)
    ui.on("shortcut_escape", _on_shortcut_escape)
    ui.on("shortcut_prev_source", _on_shortcut_prev)
    ui.on("shortcut_next_source", _on_shortcut_next)
    ui.on("shortcut_apply_code", _on_shortcut_apply_code)

    # ── Initial render ───────────────────────────────────────────────
    _render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)
    _load_notes(conn, current_source_id(), coder_id, notes_area)
    _auto_transition()


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------

def _render_text(conn, source_id, coder_id, codes_by_id, text_container):
    content_row = get_source_content(conn, source_id)
    text = content_row["content_text"] if content_row else ""
    annotations = get_annotations_for_source(conn, source_id, coder_id)
    rendered = render_annotated_text(text, annotations, codes_by_id)
    text_container.content = rendered


def _load_notes(conn, source_id, coder_id, notes_area):
    note_text = _get_note(conn, source_id, coder_id)
    notes_area.value = note_text or ""


# ---------------------------------------------------------------------------
# Navigation helper
# ---------------------------------------------------------------------------

def _go_home(conn):
    try:
        checkpoint_and_close(conn)
    except Exception:
        pass
    ui.navigate.to("/")


# ---------------------------------------------------------------------------
# Undo / redo
# ---------------------------------------------------------------------------

def _do_undo(conn, coder_id, codes_by_id, text_container, annotation_list_display, undo_mgr, source_id):
    action = undo_mgr.undo(source_id)
    if action is None:
        ui.notify("Nothing to undo.", type="info", position="bottom", timeout=1000)
        return
    ann_id = action["annotation_id"]
    if action["type"] == "undo_add":
        delete_annotation(conn, ann_id)
    elif action["type"] == "undo_delete":
        undelete_annotation(conn, ann_id)
    _render_text(conn, source_id, coder_id, codes_by_id, text_container)
    annotation_list_display.refresh()
    ui.notify("Undone.", type="info", position="bottom", timeout=1000)


def _do_redo(conn, coder_id, codes_by_id, text_container, annotation_list_display, undo_mgr, source_id):
    action = undo_mgr.redo(source_id)
    if action is None:
        ui.notify("Nothing to redo.", type="info", position="bottom", timeout=1000)
        return
    ann_id = action["annotation_id"]
    if action["type"] == "redo_add":
        undelete_annotation(conn, ann_id)
    elif action["type"] == "redo_delete":
        delete_annotation(conn, ann_id)
    _render_text(conn, source_id, coder_id, codes_by_id, text_container)
    annotation_list_display.refresh()
    ui.notify("Redone.", type="info", position="bottom", timeout=1000)


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
        build(conn)
