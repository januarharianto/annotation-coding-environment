"""Keyboard shortcut and JS event handlers for the coding page."""

from nicegui import ui

from ace.models.codebook import reorder_codes
from ace.pages.coding_actions import apply_code, do_undo_redo
from ace.pages.coding_dialogs import open_annotation_info


def register_shortcuts(
    *,
    state,
    conn,
    coder_id,
    codes,
    codes_by_id,
    undo_mgr,
    text_container,
    annotation_list_refresh,
    grid_container,
    annotation_info_dialog,
    assignments,
    current_source_id,
    navigate_to_fn,
    toggle_grid_fn,
    refresh_codes_fn,
    code_list_refresh,
    delete_annotation_fn,
):
    """Register all keyboard shortcut and JS event handlers."""

    # ── JS event handlers ─────────────────────────────────────────────

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
            open_annotation_info(conn, annotation_info_dialog, ann_ids, codes_by_id, delete_annotation_fn)

    ui.on("text_selected", _on_text_selected)
    ui.on("annotation_clicked", _on_annotation_clicked)

    # ── Keyboard shortcut handlers ────────────────────────────────────

    def _on_shortcut_undo(_e):
        do_undo_redo(conn, coder_id, codes_by_id, text_container, annotation_list_refresh, undo_mgr, current_source_id())

    def _on_shortcut_redo(_e):
        do_undo_redo(conn, coder_id, codes_by_id, text_container, annotation_list_refresh, undo_mgr, current_source_id(), redo=True)

    def _on_shortcut_escape(_e):
        if grid_container.visible:
            grid_container.set_visibility(False)
            return
        state["pending_selection"] = None
        annotation_info_dialog.close()

    def _on_shortcut_prev(_e):
        idx = state["current_index"]
        if idx > 0:
            navigate_to_fn(idx - 1)

    def _on_shortcut_next(_e):
        idx = state["current_index"]
        if idx < len(assignments) - 1:
            navigate_to_fn(idx + 1)

    async def _on_shortcut_apply_code(e):
        code_idx = e.args.get("index", -1)
        if 0 <= code_idx < len(codes):
            await apply_code(state, conn, coder_id, current_source_id, codes_by_id, text_container, annotation_list_refresh, undo_mgr, codes[code_idx])

    def _on_codes_reordered(e):
        code_ids = e.args.get("code_ids", [])
        if code_ids:
            reorder_codes(conn, code_ids)
            refresh_codes_fn()
            code_list_refresh()

    ui.on("codes_reordered", _on_codes_reordered)
    ui.on("shortcut_undo", _on_shortcut_undo)
    ui.on("shortcut_redo", _on_shortcut_redo)
    ui.on("shortcut_escape", _on_shortcut_escape)
    ui.on("shortcut_prev_source", _on_shortcut_prev)
    ui.on("shortcut_next_source", _on_shortcut_next)
    ui.on("shortcut_apply_code", _on_shortcut_apply_code)
    ui.on("shortcut_toggle_grid", lambda _e: toggle_grid_fn())
