"""Action functions extracted from the coding page build()."""

from nicegui import ui

from ace.models.annotation import (
    add_annotation,
    delete_annotation,
    get_annotations_for_source,
    undelete_annotation,
)
from ace.models.assignment import update_assignment_status
from ace.models.source import get_source_content
from ace.services.offset import utf16_to_codepoint


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------

def render_text(conn, source_id, coder_id, codes_by_id, text_container):
    from ace.pages.coding import render_annotated_text

    content_row = get_source_content(conn, source_id)
    text = content_row["content_text"] if content_row else ""
    annotations = get_annotations_for_source(conn, source_id, coder_id)
    rendered = render_annotated_text(text, annotations, codes_by_id)
    text_container.content = rendered


# ---------------------------------------------------------------------------
# Apply code
# ---------------------------------------------------------------------------

async def apply_code(state, conn, coder_id, source_id_fn, codes_by_id, text_container, annotation_list_refresh, undo_mgr, code):
    sel = state.get("pending_selection")
    if not sel:
        # Fallback: read snapshot captured on last mousedown
        sel = await ui.run_javascript("window.__aceLastSelection")
        if sel:
            state["pending_selection"] = sel
    if not sel:
        ui.notify("Select text first, then click a code.", type="info", position="bottom", timeout=2000)
        return

    source_id = source_id_fn()
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
    render_text(conn, source_id, coder_id, codes_by_id, text_container)
    annotation_list_refresh()


# ---------------------------------------------------------------------------
# Delete annotation
# ---------------------------------------------------------------------------

def delete_annotation_action(conn, ann, undo_mgr, codes_by_id, coder_id, text_container, annotation_list_refresh, dialog=None):
    source_id = ann["source_id"]
    undo_mgr.record_delete(source_id, ann["id"])
    delete_annotation(conn, ann["id"])
    if dialog:
        dialog.close()
    render_text(conn, source_id, coder_id, codes_by_id, text_container)
    annotation_list_refresh()
    ui.notify("Annotation removed.", type="info", position="bottom", timeout=1500)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def navigate_to(conn, coder_id, state, assignments, codes_by_id, text_container, source_header_refresh, bottom_bar_refresh, annotation_list_refresh, reload_assignments_fn, idx):
    if idx == state["current_index"]:
        return

    # Auto-complete the departing source (unless already complete or flagged)
    departing = assignments[state["current_index"]]
    if departing["status"] not in ("complete", "flagged"):
        update_assignment_status(conn, departing["source_id"], coder_id, "complete")

    state["current_index"] = idx
    state["pending_selection"] = None

    asn = assignments[idx]
    source_id = asn["source_id"]

    if asn["status"] == "pending":
        update_assignment_status(conn, source_id, coder_id, "in_progress")

    reload_assignments_fn()

    render_text(conn, source_id, coder_id, codes_by_id, text_container)
    source_header_refresh()
    bottom_bar_refresh()
    annotation_list_refresh()


# ---------------------------------------------------------------------------
# Flag toggle
# ---------------------------------------------------------------------------

def toggle_flag(conn, coder_id, state, assignments, source_header_refresh, bottom_bar_refresh, reload_assignments_fn):
    asn = assignments[state["current_index"]]
    new_status = "in_progress" if asn["status"] == "flagged" else "flagged"
    update_assignment_status(conn, asn["source_id"], coder_id, new_status)
    reload_assignments_fn()
    source_header_refresh()
    bottom_bar_refresh()


# ---------------------------------------------------------------------------
# Undo / redo
# ---------------------------------------------------------------------------

_UNDO_OPS = {"undo_add": "delete", "undo_delete": "undelete"}
_REDO_OPS = {"redo_add": "undelete", "redo_delete": "delete"}


def do_undo_redo(conn, coder_id, codes_by_id, text_container, annotation_list_refresh, undo_mgr, source_id, *, redo=False):
    label = "redo" if redo else "undo"
    action = (undo_mgr.redo if redo else undo_mgr.undo)(source_id)
    if action is None:
        ui.notify(f"Nothing to {label}.", type="info", position="bottom", timeout=1000)
        return
    ops = _REDO_OPS if redo else _UNDO_OPS
    op = ops.get(action["type"])
    if op == "delete":
        delete_annotation(conn, action["annotation_id"])
    elif op == "undelete":
        undelete_annotation(conn, action["annotation_id"])
    render_text(conn, source_id, coder_id, codes_by_id, text_container)
    annotation_list_refresh()
    ui.notify(f"{label.title()}.", type="info", position="bottom", timeout=1000)


# ---------------------------------------------------------------------------
# Auto-transition
# ---------------------------------------------------------------------------

def auto_transition(conn, coder_id, state, assignments, reload_assignments_fn):
    asn = assignments[state["current_index"]]
    if asn["status"] == "pending":
        update_assignment_status(conn, asn["source_id"], coder_id, "in_progress")
        reload_assignments_fn()
