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
            for hex_colour, _ in COLOUR_PALETTE:
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


def open_new_group_dialog(dlg, on_create):
    """Dialog to create a new group name."""
    dlg.clear()
    with dlg, ui.card().classes("q-pa-md").style("min-width: 300px;"):
        ui.label("New Group").classes("text-subtitle1 text-weight-medium q-mb-sm")
        name_input = ui.input("Group name").props("autofocus outlined dense")

        def _create():
            name = name_input.value.strip()
            if not name:
                return
            dlg.close()
            on_create(name)

        with ui.row().classes("q-mt-md justify-end full-width gap-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")
            ui.button("Create", on_click=_create).props("unelevated color=primary")
    dlg.open()
