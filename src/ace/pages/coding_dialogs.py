"""Dialog factories for the coding page."""

import sqlite3

from nicegui import ui

from ace.models.codebook import update_code, delete_code
from ace.services.palette import COLOUR_PALETTE


def open_code_dialog(dlg, title, content_fn, action_label=None, action_fn=None, action_props="unelevated color=primary"):
    """Generic dialog factory: clear, populate, and open a dialog."""
    dlg.clear()
    with dlg, ui.card().classes("q-pa-md").style("min-width: 300px;"):
        ui.label(title).classes("text-subtitle1 text-weight-medium q-mb-sm")
        content_fn()
        with ui.row().classes("q-mt-md justify-end full-width gap-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")
            if action_label:
                ui.button(action_label, on_click=action_fn).props(action_props)
    dlg.open()


def open_rename_dialog(conn: sqlite3.Connection, dlg, code, refresh_all_fn):
    """Rename-code dialog."""
    name_input = None

    def _content():
        nonlocal name_input
        name_input = ui.input("Name", value=code["name"]).props("autofocus outlined dense")

    def _save():
        new_name = name_input.value.strip()
        if not new_name:
            return
        update_code(conn, code["id"], name=new_name)
        dlg.close()
        refresh_all_fn()

    open_code_dialog(dlg, "Rename Code", _content, "Save", _save)


def open_colour_dialog(conn: sqlite3.Connection, dlg, code, refresh_all_fn):
    """Colour-picker dialog."""
    def _content():
        ui.label(code["name"]).classes("text-body2 text-grey-7 q-mb-sm")
        with ui.row().classes("gap-2").style("flex-wrap: wrap;"):
            for hex_colour, colour_name in COLOUR_PALETTE:
                def _pick(c=hex_colour):
                    update_code(conn, code["id"], colour=c)
                    dlg.close()
                    refresh_all_fn()

                is_current = (code["colour"] or "").lower() == hex_colour.lower()
                ui.element("div").classes("ace-code-dot cursor-pointer").style(
                    f"background-color: {hex_colour}; width: 28px; height: 28px; "
                    f"border: {'3px solid #333' if is_current else '2px solid transparent'};"
                ).tooltip(hex_colour).on("click", _pick)

    open_code_dialog(dlg, "Change Colour", _content)


def open_delete_dialog(conn: sqlite3.Connection, dlg, code, refresh_all_fn):
    """Delete-code confirmation dialog."""
    def _content():
        ui.label(
            f'Are you sure you want to delete "{code["name"]}"?'
        ).classes("text-body2 q-mb-sm")
        ui.label(
            "All annotations using this code will be permanently deleted."
        ).classes("text-caption text-grey-7 q-mb-md")

    def _confirm():
        delete_code(conn, code["id"])
        dlg.close()
        refresh_all_fn()

    open_code_dialog(dlg, "Delete Code", _content, "Delete", _confirm, "unelevated color=negative")


def open_annotation_info(conn: sqlite3.Connection, dlg, ann_ids, codes_by_id, delete_annotation_fn):
    """Annotation info popup showing stacked annotations at a click point."""
    anns = []
    for aid in ann_ids:
        row = conn.execute(
            "SELECT * FROM annotation WHERE id = ? AND deleted_at IS NULL", (aid,)
        ).fetchone()
        if row:
            anns.append(row)

    if not anns:
        return

    dlg.clear()
    with dlg, ui.card().classes("q-pa-sm").style("min-width: 250px;"):
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
                    on_click=lambda _e, a=ann: delete_annotation_fn(a, dlg),
                ).props("flat round dense size=sm color=negative")

        ui.button("Close", on_click=dlg.close).props("flat dense").classes("q-mt-xs")

    dlg.open()
