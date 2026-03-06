"""Coder annotation interface — the main screen for annotating text."""

import html
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from nicegui import app, events, ui

from ace.db.connection import checkpoint_and_close, open_project
from ace.models.annotation import (
    add_annotation,
    delete_annotation,
    get_annotations_for_source,
)
from ace.models.assignment import get_assignments_for_coder, update_assignment_status
from ace.models.codebook import list_codes
from ace.models.coder import list_coders
from ace.models.project import get_project
from ace.models.source import get_source, get_source_content
from ace.services.offset import codepoint_to_utf16, utf16_to_codepoint


# ---------------------------------------------------------------------------
# Source note helpers (the schema has a source_note table but no model funcs)
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

def render_annotated_text(text: str, annotations: list, codes_by_id: dict) -> str:
    """Build HTML from plain text + annotations with coloured spans.

    Handles overlapping annotations via an event-based sweep.
    """
    if not text:
        return ""

    # Build open/close events
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

    # Sort: by offset, then closes before opens at same offset
    events_list.sort(key=lambda e: (e[0], e[1]))

    parts: list[str] = []
    pos = 0
    open_stack: list[dict] = []

    for offset, kind_order, kind, data in events_list:
        # Emit text from pos to offset
        if offset > pos:
            parts.append(html.escape(text[pos:offset]))
            pos = offset

        if kind == "open":
            # Convert colour to rgba with transparency
            hex_c = data["colour"].lstrip("#")
            if len(hex_c) == 6:
                r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
            else:
                r, g, b = 153, 153, 153
            parts.append(
                f'<span class="ace-annotation" '
                f'data-annotation-id="{html.escape(data["id"])}" '
                f'title="{html.escape(data["code_name"])}" '
                f'style="background-color: rgba({r},{g},{b},0.3);">'
            )
            open_stack.append(data)
        else:
            # Close — find and close the matching span
            # We need to close spans in reverse order (innermost first)
            # and re-open the ones that aren't being closed
            target_id = data["id"]
            # Find index in stack
            idx = None
            for i in range(len(open_stack) - 1, -1, -1):
                if open_stack[i]["id"] == target_id:
                    idx = i
                    break
            if idx is not None:
                # Close everything from top of stack down to idx
                to_reopen = []
                for i in range(len(open_stack) - 1, idx, -1):
                    parts.append("</span>")
                    to_reopen.append(open_stack[i])
                # Close the target
                parts.append("</span>")
                open_stack.pop(idx)
                # Re-open the ones above
                for item in reversed(to_reopen):
                    hex_c = item["colour"].lstrip("#")
                    if len(hex_c) == 6:
                        r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
                    else:
                        r, g, b = 153, 153, 153
                    parts.append(
                        f'<span class="ace-annotation" '
                        f'data-annotation-id="{html.escape(item["id"])}" '
                        f'title="{html.escape(item["code_name"])}" '
                        f'style="background-color: rgba({r},{g},{b},0.3);">'
                    )

    # Remaining text
    if pos < len(text):
        parts.append(html.escape(text[pos:]))

    # Close any remaining open spans
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
# Main builder
# ---------------------------------------------------------------------------

def build(conn: sqlite3.Connection) -> None:
    """Build the full coder annotation interface."""

    project = get_project(conn)
    coders = list_coders(conn)
    if not coders:
        ui.label("No coder found in this project file.").classes("text-h6 q-pa-md")
        return

    coder = coders[0]
    coder_id = coder["id"]
    codes = list_codes(conn)
    codes_by_id = {c["id"]: c for c in codes}

    assignments = get_assignments_for_coder(conn, coder_id)
    if not assignments:
        ui.label("No assignments found for this coder.").classes("text-h6 q-pa-md")
        return

    # State tracking
    state = {
        "current_index": 0,
        "pending_selection": None,  # {start, end, text}
    }

    # Find first pending/in_progress source, or first source
    for i, a in enumerate(assignments):
        if a["status"] in ("pending", "in_progress"):
            state["current_index"] = i
            break

    def current_assignment():
        return assignments[state["current_index"]]

    def current_source_id():
        return current_assignment()["source_id"]

    def _auto_transition():
        """Auto-transition pending -> in_progress."""
        asn = current_assignment()
        if asn["status"] == "pending":
            update_assignment_status(conn, asn["source_id"], coder_id, "in_progress")
            # Refresh assignments list
            _reload_assignments()

    def _reload_assignments():
        """Reload the assignments list from DB."""
        fresh = get_assignments_for_coder(conn, coder_id)
        assignments.clear()
        assignments.extend(fresh)

    # ── Layout ────────────────────────────────────────────────────────
    # Include static CSS/JS
    ui.add_head_html('<link rel="stylesheet" href="/static/css/annotator.css">')
    ui.add_head_html('<script src="/static/js/bridge.js" defer></script>')

    # Code picker dialog (shared across interactions)
    code_picker_dialog = ui.dialog()
    annotation_info_dialog = ui.dialog()

    # ── Main container ────────────────────────────────────────────────
    with ui.row().classes("full-width").style("height: calc(100vh - 80px); overflow: hidden;"):

        # ── Left Sidebar ──────────────────────────────────────────────
        with ui.column().classes("q-pa-md").style(
            "width: 280px; min-width: 280px; overflow-y: auto; border-right: 1px solid #e0e0e0;"
        ):
            # Back button
            ui.button(icon="arrow_back", on_click=lambda: _go_home(conn)).props(
                "flat round dense"
            ).tooltip("Back to home")

            ui.label(project["name"] if project else "Project").classes(
                "text-subtitle1 text-weight-medium q-mt-sm"
            )

            # Instructions (collapsible)
            if project and project["instructions"]:
                with ui.expansion("Instructions", icon="info").classes("full-width q-mt-xs"):
                    ui.label(project["instructions"]).classes(
                        "text-body2 text-grey-8"
                    ).style("white-space: pre-wrap;")

            ui.separator().classes("q-my-sm")

            # ── Code list ─────────────────────────────────────────────
            ui.label("Codes").classes("text-subtitle2 text-weight-medium")

            for i, code in enumerate(codes):
                shortcut = str(i + 1) if i < 9 else ""
                colour = code["colour"] or "#999999"
                with ui.row().classes("items-center q-py-xs cursor-pointer").style(
                    "gap: 8px;"
                ).on(
                    "click",
                    lambda _e, c=code: _apply_code(c, state, conn, coder_id, codes_by_id, text_container, annotation_list_display),
                ):
                    ui.element("div").classes("ace-code-dot").style(
                        f"background-color: {colour};"
                    )
                    lbl = ui.label(code["name"]).classes("text-body2 col")
                    if code["description"]:
                        lbl.tooltip(code["description"])
                    if shortcut:
                        ui.label(shortcut).classes(
                            "text-caption text-grey-5"
                        ).style(
                            "background: #eee; border-radius: 3px; padding: 0 5px; font-family: monospace;"
                        )

            ui.separator().classes("q-my-sm")

            # ── Source list (collapsible) ──────────────────────────────
            with ui.expansion("Sources", icon="description", value=False).classes(
                "full-width"
            ):
                @ui.refreshable
                def source_list():
                    for i, asn in enumerate(assignments):
                        status = asn["status"]
                        icon_name, icon_colour = _STATUS_ICONS.get(
                            status, ("help", "grey")
                        )
                        active_cls = "active" if i == state["current_index"] else ""
                        with ui.row().classes(
                            f"items-center ace-source-item {active_cls} full-width"
                        ).on(
                            "click",
                            lambda _e, idx=i: _navigate_to(idx, state, conn, coder_id, codes_by_id, text_container, annotation_list_display, notes_area, source_header, bottom_bar, source_list),
                        ):
                            ui.icon(icon_name).style(
                                f"color: {icon_colour}; font-size: 1rem;"
                            )
                            ui.label(asn["display_id"]).classes(
                                "text-body2 ellipsis col"
                            )

                source_list()

        # ── Centre Panel ──────────────────────────────────────────────
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

                # Metadata
                if src["metadata_json"]:
                    try:
                        meta = json.loads(src["metadata_json"])
                        with ui.row().classes("q-mb-sm gap-2"):
                            for k, v in meta.items():
                                ui.label(f"{k}: {v}").classes(
                                    "text-caption text-grey-7 bg-grey-2 q-px-xs"
                                ).style("border-radius: 3px;")
                    except (json.JSONDecodeError, TypeError):
                        pass

            source_header()

            # Text content area
            text_container = ui.html("").classes("full-width")

            ui.separator().classes("q-my-sm")

            # Annotation list for current source
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
                                on_click=lambda _e, a=ann: _delete_annotation(
                                    a, conn, coder_id, codes_by_id, text_container, annotation_list_display
                                ),
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
                    on_click=lambda: _navigate_to(
                        max(0, idx - 1), state, conn, coder_id, codes_by_id,
                        text_container, annotation_list_display, notes_area, source_header, bottom_bar, source_list
                    ),
                ).props("flat dense" + (" disable" if idx == 0 else ""))

                ui.label(
                    f"Source {idx + 1} of {total} ({pct}% complete)"
                ).classes("text-body2 text-grey-8")

                ui.button(
                    "Next",
                    icon="chevron_right",
                    on_click=lambda: _navigate_to(
                        min(total - 1, idx + 1), state, conn, coder_id, codes_by_id,
                        text_container, annotation_list_display, notes_area, source_header, bottom_bar, source_list
                    ),
                ).props("flat dense" + (" disable" if idx >= total - 1 else "")).classes("q-mr-md")

            # Status buttons
            with ui.row().classes("items-center gap-2"):
                is_complete = asn["status"] == "complete"
                ui.button(
                    "Completed" if is_complete else "Mark Complete",
                    icon="check_circle" if is_complete else "check_circle_outline",
                    on_click=lambda: _toggle_complete(
                        conn, coder_id, state, assignments, source_header, bottom_bar, source_list
                    ),
                ).props(
                    f"{'unelevated color=positive' if is_complete else 'outline'} dense"
                )

                is_flagged = asn["status"] == "flagged"
                ui.button(
                    "Flagged" if is_flagged else "Flag",
                    icon="flag",
                    on_click=lambda: _toggle_flag(
                        conn, coder_id, state, assignments, source_header, bottom_bar, source_list
                    ),
                ).props(
                    f"{'unelevated color=negative' if is_flagged else 'outline'} dense"
                )

    bottom_bar()

    # ── Event handlers from JS ────────────────────────────────────────
    def _on_text_selected(e):
        data = e.args
        state["pending_selection"] = {
            "start": data["start"],
            "end": data["end"],
            "text": data["text"],
        }
        _open_code_picker(
            state, conn, coder_id, codes, codes_by_id,
            text_container, annotation_list_display, code_picker_dialog,
        )

    def _on_annotation_clicked(e):
        data = e.args
        ann_ids = data.get("annotation_ids", [])
        if ann_ids:
            _open_annotation_info(
                ann_ids, conn, coder_id, codes_by_id,
                text_container, annotation_list_display, annotation_info_dialog,
            )

    ui.on("text_selected", _on_text_selected)
    ui.on("annotation_clicked", _on_annotation_clicked)

    # ── Initial render ────────────────────────────────────────────────
    _render_text(conn, current_source_id(), coder_id, codes_by_id, text_container)
    _load_notes(conn, current_source_id(), coder_id, notes_area)
    _auto_transition()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def _navigate_to(
    idx, state, conn, coder_id, codes_by_id,
    text_container, annotation_list_display, notes_area, source_header, bottom_bar, source_list,
):
    if idx == state["current_index"]:
        return
    # Save current notes before navigating
    assignments = get_assignments_for_coder(conn, coder_id)

    state["current_index"] = idx
    state["pending_selection"] = None

    asn = assignments[idx]
    source_id = asn["source_id"]

    # Auto-transition pending -> in_progress
    if asn["status"] == "pending":
        update_assignment_status(conn, source_id, coder_id, "in_progress")
        # Refresh assignments
        fresh = get_assignments_for_coder(conn, coder_id)
        assignments.clear()
        assignments.extend(fresh)

    _render_text(conn, source_id, coder_id, codes_by_id, text_container)
    _load_notes(conn, source_id, coder_id, notes_area)
    source_header.refresh()
    bottom_bar.refresh()
    source_list.refresh()
    annotation_list_display.refresh()


def _go_home(conn):
    try:
        checkpoint_and_close(conn)
    except Exception:
        pass
    ui.navigate.to("/")


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------

def _render_text(conn, source_id, coder_id, codes_by_id, text_container):
    content_row = get_source_content(conn, source_id)
    text = content_row["content_text"] if content_row else ""
    annotations = get_annotations_for_source(conn, source_id, coder_id)
    rendered = render_annotated_text(text, annotations, codes_by_id)
    text_container.content = f'<div id="ace-text-content">{rendered}</div>'


def _load_notes(conn, source_id, coder_id, notes_area):
    note_text = _get_note(conn, source_id, coder_id)
    notes_area.value = note_text or ""


# ---------------------------------------------------------------------------
# Code picker / apply code
# ---------------------------------------------------------------------------

def _open_code_picker(
    state, conn, coder_id, codes, codes_by_id,
    text_container, annotation_list_display, dialog,
):
    sel = state.get("pending_selection")
    if not sel:
        return

    dialog.clear()
    with dialog, ui.card().classes("q-pa-sm").style("min-width: 250px;"):
        ui.label("Apply code").classes("text-subtitle2 text-weight-medium q-mb-xs")
        selected_preview = sel["text"][:80] + ("..." if len(sel["text"]) > 80 else "")
        ui.label(f'"{selected_preview}"').classes("text-caption text-grey-7 q-mb-sm")

        for i, code in enumerate(codes):
            colour = code["colour"] or "#999999"
            shortcut = str(i + 1) if i < 9 else ""
            with ui.row().classes(
                "items-center q-py-xs cursor-pointer full-width"
            ).style("gap: 8px;").on(
                "click",
                lambda _e, c=code: _do_apply_code(
                    c, sel, state, conn, coder_id, codes_by_id,
                    text_container, annotation_list_display, dialog,
                ),
            ):
                ui.element("div").classes("ace-code-dot").style(
                    f"background-color: {colour};"
                )
                ui.label(code["name"]).classes("text-body2 col")
                if shortcut:
                    ui.label(shortcut).classes(
                        "text-caption text-grey-5"
                    ).style(
                        "background: #eee; border-radius: 3px; padding: 0 5px; font-family: monospace;"
                    )

        ui.button("Cancel", on_click=dialog.close).props("flat dense").classes("q-mt-xs")

    dialog.open()


def _do_apply_code(
    code, sel, state, conn, coder_id, codes_by_id,
    text_container, annotation_list_display, dialog,
):
    source_id = get_assignments_for_coder(conn, coder_id)[state["current_index"]]["source_id"]

    # Get the text content for offset conversion
    content_row = get_source_content(conn, source_id)
    text = content_row["content_text"] if content_row else ""

    # JavaScript gives us character offsets (UTF-16 code units in the browser).
    # Convert to Python codepoint offsets if there are surrogate pairs.
    start_cp = utf16_to_codepoint(text, sel["start"])
    end_cp = utf16_to_codepoint(text, sel["end"])

    selected_text = text[start_cp:end_cp]

    add_annotation(
        conn,
        source_id=source_id,
        coder_id=coder_id,
        code_id=code["id"],
        start_offset=start_cp,
        end_offset=end_cp,
        selected_text=selected_text,
    )

    state["pending_selection"] = None
    dialog.close()

    _render_text(conn, source_id, coder_id, codes_by_id, text_container)
    annotation_list_display.refresh()
    ui.notify(f"Applied: {code['name']}", type="positive", position="bottom", timeout=1500)


def _apply_code(code, state, conn, coder_id, codes_by_id, text_container, annotation_list_display):
    """Apply code from sidebar click (only if there's a pending selection)."""
    sel = state.get("pending_selection")
    if not sel:
        ui.notify("Select text first, then click a code.", type="info", position="bottom", timeout=2000)
        return

    source_id = get_assignments_for_coder(conn, coder_id)[state["current_index"]]["source_id"]

    content_row = get_source_content(conn, source_id)
    text = content_row["content_text"] if content_row else ""

    start_cp = utf16_to_codepoint(text, sel["start"])
    end_cp = utf16_to_codepoint(text, sel["end"])
    selected_text = text[start_cp:end_cp]

    add_annotation(
        conn,
        source_id=source_id,
        coder_id=coder_id,
        code_id=code["id"],
        start_offset=start_cp,
        end_offset=end_cp,
        selected_text=selected_text,
    )

    state["pending_selection"] = None
    _render_text(conn, source_id, coder_id, codes_by_id, text_container)
    annotation_list_display.refresh()
    ui.notify(f"Applied: {code['name']}", type="positive", position="bottom", timeout=1500)


# ---------------------------------------------------------------------------
# Annotation info / delete
# ---------------------------------------------------------------------------

def _open_annotation_info(
    ann_ids, conn, coder_id, codes_by_id,
    text_container, annotation_list_display, dialog,
):
    anns = []
    for aid in ann_ids:
        row = conn.execute(
            "SELECT * FROM annotation WHERE id = ? AND deleted_at IS NULL", (aid,)
        ).fetchone()
        if row:
            anns.append(row)

    if not anns:
        return

    dialog.clear()
    with dialog, ui.card().classes("q-pa-sm").style("min-width: 250px;"):
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
                    on_click=lambda _e, a=ann: _delete_annotation_from_dialog(
                        a, conn, coder_id, codes_by_id,
                        text_container, annotation_list_display, dialog,
                    ),
                ).props("flat round dense size=sm color=negative")

        ui.button("Close", on_click=dialog.close).props("flat dense").classes("q-mt-xs")

    dialog.open()


def _delete_annotation_from_dialog(
    ann, conn, coder_id, codes_by_id,
    text_container, annotation_list_display, dialog,
):
    source_id = ann["source_id"]
    delete_annotation(conn, ann["id"])
    dialog.close()
    _render_text(conn, source_id, coder_id, codes_by_id, text_container)
    annotation_list_display.refresh()
    ui.notify("Annotation removed.", type="info", position="bottom", timeout=1500)


def _delete_annotation(ann, conn, coder_id, codes_by_id, text_container, annotation_list_display):
    source_id = ann["source_id"]
    delete_annotation(conn, ann["id"])
    _render_text(conn, source_id, coder_id, codes_by_id, text_container)
    annotation_list_display.refresh()
    ui.notify("Annotation removed.", type="info", position="bottom", timeout=1500)


# ---------------------------------------------------------------------------
# Status toggles
# ---------------------------------------------------------------------------

def _toggle_complete(conn, coder_id, state, assignments, source_header, bottom_bar, source_list):
    asn = assignments[state["current_index"]]
    new_status = "in_progress" if asn["status"] == "complete" else "complete"
    update_assignment_status(conn, asn["source_id"], coder_id, new_status)
    _reload_and_refresh(conn, coder_id, assignments, source_header, bottom_bar, source_list)


def _toggle_flag(conn, coder_id, state, assignments, source_header, bottom_bar, source_list):
    asn = assignments[state["current_index"]]
    new_status = "in_progress" if asn["status"] == "flagged" else "flagged"
    update_assignment_status(conn, asn["source_id"], coder_id, new_status)
    _reload_and_refresh(conn, coder_id, assignments, source_header, bottom_bar, source_list)


def _reload_and_refresh(conn, coder_id, assignments, source_header, bottom_bar, source_list):
    fresh = get_assignments_for_coder(conn, coder_id)
    assignments.clear()
    assignments.extend(fresh)
    source_header.refresh()
    bottom_bar.refresh()
    source_list.refresh()
