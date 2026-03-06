"""Codebook step component for the manager wizard."""

import shutil
import tempfile
from pathlib import Path

from nicegui import events, ui

from ace.models.codebook import (
    add_code,
    delete_code,
    import_codebook_from_csv,
    list_codes,
    update_code,
)
from ace.models.project import get_project, update_instructions

# Colour-blind accessible palette
COLOUR_PALETTE = [
    ("#E69F00", "Orange"),
    ("#56B4E9", "Sky blue"),
    ("#009E73", "Teal"),
    ("#F0E442", "Yellow"),
    ("#0072B2", "Blue"),
    ("#D55E00", "Red-orange"),
    ("#CC79A7", "Pink"),
    ("#999999", "Grey"),
    ("#332288", "Indigo"),
    ("#44AA99", "Cyan"),
]


def build(conn, stepper) -> None:
    """Build the Codebook step UI inside the current stepper step context.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection for the current project.
    stepper : ui.stepper
        The parent stepper widget, used to navigate between steps.
    """

    def _is_locked():
        project = get_project(conn)
        return bool(project["codebook_hash"]) if project else False

    # -- Code list --
    ui.label("Codes").classes("text-subtitle1 text-weight-medium")

    @ui.refreshable
    def code_list():
        codes = list_codes(conn)
        locked = _is_locked()

        if not codes:
            ui.label("No codes defined yet. Add a code or import from CSV.").classes(
                "text-body2 text-grey-7 q-my-sm"
            )
        else:
            for code in codes:
                _code_row(conn, code, locked, code_list)

    code_list()

    # -- Action buttons --
    with ui.row().classes("q-mt-md gap-2"):
        ui.button("Add code", icon="add", on_click=lambda: _open_add_dialog(conn, code_list)).props(
            "outline"
        )
        ui.button("Import from CSV", icon="upload_file", on_click=lambda: _open_import_dialog(conn, code_list)).props(
            "outline"
        )

    ui.separator().classes("q-my-md")

    # -- Project instructions --
    ui.label("Project instructions").classes("text-subtitle1 text-weight-medium")
    ui.label("Free-text instructions visible to all coders.").classes(
        "text-body2 text-grey-7 q-mb-sm"
    )

    project = get_project(conn)
    current_instructions = project["instructions"] if project and project["instructions"] else ""

    instructions_area = ui.textarea(
        value=current_instructions,
        placeholder="Enter coding instructions for your team...",
    ).classes("full-width").props("outlined autogrow")

    def _save_instructions():
        update_instructions(conn, instructions_area.value or "")
        ui.notify("Instructions saved.", type="positive")

    ui.button("Save instructions", icon="save", on_click=_save_instructions).props("outline")

    # -- Navigation --
    with ui.row().classes("q-mt-md gap-2"):
        ui.button("Back", on_click=stepper.previous).props("flat")
        ui.button("Next: Assign & Export", icon="arrow_forward", on_click=stepper.next).props(
            "unelevated"
        )


def _code_row(conn, code, locked, code_list_refreshable):
    """Render a single code row with colour dot, name, description, and actions."""
    with ui.card().classes("full-width q-mb-xs").props("flat bordered"):
        with ui.row().classes("items-center full-width q-pa-sm no-wrap"):
            # Colour dot
            ui.icon("circle").style(f"color: {code['colour'] or '#999999'}; font-size: 1.2rem")

            # Name and description
            with ui.column().classes("col q-ml-sm").style("min-width: 0"):
                ui.label(code["name"]).classes("text-body1 text-weight-medium")
                desc = code["description"] or ""
                if desc:
                    truncated = desc[:80] + ("..." if len(desc) > 80 else "")
                    ui.label(truncated).classes("text-caption text-grey-7")

            # Sort order
            ui.label(f"#{code['sort_order']}").classes("text-caption text-grey-5 q-mx-sm")

            # Edit button
            ui.button(
                icon="edit",
                on_click=lambda c=code: _open_edit_dialog(conn, c, code_list_refreshable),
            ).props("flat round dense size=sm")

            # Delete button
            if locked:
                btn = ui.button(icon="delete").props("flat round dense size=sm disable")
                btn.tooltip("Cannot delete codes after coder packages have been exported")
            else:
                ui.button(
                    icon="delete",
                    on_click=lambda c=code: _open_delete_dialog(conn, c, code_list_refreshable),
                ).props("flat round dense size=sm color=negative")


def _open_add_dialog(conn, code_list_refreshable):
    """Open a dialog to add a new code."""
    state = {"colour": COLOUR_PALETTE[0][0]}

    with ui.dialog() as dialog, ui.card().classes("q-pa-md").style("min-width: 400px"):
        ui.label("Add code").classes("text-h6 q-mb-md")

        name_input = ui.input("Name", placeholder="Code name").props("outlined").classes("full-width")

        ui.label("Colour").classes("text-body2 q-mt-sm q-mb-xs")
        _colour_picker(state)

        desc_input = ui.textarea("Description (optional)", placeholder="Describe this code...").props(
            "outlined autogrow"
        ).classes("full-width q-mt-sm")

        with ui.row().classes("q-mt-md justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            def _do_add():
                name = (name_input.value or "").strip()
                if not name:
                    ui.notify("Name is required.", type="warning")
                    return
                try:
                    add_code(conn, name=name, colour=state["colour"], description=desc_input.value or None)
                except Exception as exc:
                    ui.notify(f"Error: {exc}", type="negative")
                    return
                ui.notify(f"Code '{name}' added.", type="positive")
                dialog.close()
                code_list_refreshable.refresh()

            ui.button("Add", icon="add", on_click=_do_add).props("unelevated")

    dialog.open()


def _open_edit_dialog(conn, code, code_list_refreshable):
    """Open a dialog to edit an existing code."""
    state = {"colour": code["colour"] or COLOUR_PALETTE[0][0]}

    with ui.dialog() as dialog, ui.card().classes("q-pa-md").style("min-width: 400px"):
        ui.label("Edit code").classes("text-h6 q-mb-md")

        name_input = ui.input("Name", value=code["name"]).props("outlined").classes("full-width")

        ui.label("Colour").classes("text-body2 q-mt-sm q-mb-xs")
        _colour_picker(state)

        desc_input = ui.textarea(
            "Description", value=code["description"] or ""
        ).props("outlined autogrow").classes("full-width q-mt-sm")

        with ui.row().classes("q-mt-md justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            def _do_save():
                name = (name_input.value or "").strip()
                if not name:
                    ui.notify("Name is required.", type="warning")
                    return
                try:
                    update_code(
                        conn,
                        code["id"],
                        name=name,
                        colour=state["colour"],
                        description=desc_input.value or None,
                    )
                except Exception as exc:
                    ui.notify(f"Error: {exc}", type="negative")
                    return
                ui.notify(f"Code '{name}' updated.", type="positive")
                dialog.close()
                code_list_refreshable.refresh()

            ui.button("Save", icon="save", on_click=_do_save).props("unelevated")

    dialog.open()


def _open_delete_dialog(conn, code, code_list_refreshable):
    """Open a confirmation dialog to delete a code."""
    with ui.dialog() as dialog, ui.card().classes("q-pa-md"):
        ui.label("Delete code?").classes("text-h6 q-mb-sm")
        ui.label(f'Are you sure you want to delete "{code["name"]}"?').classes("text-body1")
        ui.label("This action cannot be undone.").classes("text-caption text-grey-7")

        with ui.row().classes("q-mt-md justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            def _do_delete():
                try:
                    delete_code(conn, code["id"])
                except Exception as exc:
                    ui.notify(f"Error: {exc}", type="negative")
                    return
                ui.notify(f"Code '{code['name']}' deleted.", type="positive")
                dialog.close()
                code_list_refreshable.refresh()

            ui.button("Delete", icon="delete", on_click=_do_delete).props("unelevated color=negative")

    dialog.open()


def _open_import_dialog(conn, code_list_refreshable):
    """Open a dialog to import codes from a CSV file."""

    with ui.dialog() as dialog, ui.card().classes("q-pa-md").style("min-width: 400px"):
        ui.label("Import codebook from CSV").classes("text-h6 q-mb-sm")
        ui.label("Upload a CSV file with columns: name, colour, description").classes(
            "text-body2 text-grey-7 q-mb-md"
        )

        def _handle_upload(e: events.UploadEventArguments):
            name = e.name
            suffix = Path(name).suffix.lower()
            if suffix != ".csv":
                ui.notify("Please upload a CSV file.", type="warning")
                return

            tmp_dir = Path(tempfile.mkdtemp())
            dest = tmp_dir / name
            with open(dest, "wb") as f:
                shutil.copyfileobj(e.content, f)

            try:
                count = import_codebook_from_csv(conn, dest)
                ui.notify(f"Imported {count} code(s) from {name}.", type="positive")
                dialog.close()
                code_list_refreshable.refresh()
            except Exception as exc:
                ui.notify(f"Import failed: {exc}", type="negative")
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        ui.upload(
            label="Drop CSV here (or click to browse)",
            auto_upload=True,
            on_upload=_handle_upload,
        ).props('accept=".csv" flat bordered').classes("full-width")

        with ui.row().classes("q-mt-md justify-end"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

    dialog.open()


def _colour_picker(state):
    """Render clickable colour swatches and update state['colour'] on selection."""
    with ui.row().classes("gap-1 q-mb-xs") as row:
        for hex_colour, label in COLOUR_PALETTE:
            btn = ui.button(
                on_click=lambda _e, h=hex_colour: _select_colour(state, h, row),
            ).style(
                f"background-color: {hex_colour} !important; "
                f"min-width: 32px; width: 32px; height: 32px; padding: 0; "
                f"border-radius: 4px;"
            ).props("unelevated dense")
            btn.tooltip(label)
            # Mark currently selected
            if hex_colour == state["colour"]:
                btn.style(add="outline: 3px solid #333; outline-offset: 2px;")


def _select_colour(state, hex_colour, row):
    """Update the selected colour and re-style swatches."""
    state["colour"] = hex_colour
    # Update outlines on all swatch buttons
    for i, child in enumerate(row):
        if i < len(COLOUR_PALETTE):
            palette_hex = COLOUR_PALETTE[i][0]
            if palette_hex == hex_colour:
                child.style(
                    f"background-color: {palette_hex} !important; "
                    f"min-width: 32px; width: 32px; height: 32px; padding: 0; "
                    f"border-radius: 4px; "
                    f"outline: 3px solid #333; outline-offset: 2px;"
                )
            else:
                child.style(
                    f"background-color: {palette_hex} !important; "
                    f"min-width: 32px; width: 32px; height: 32px; padding: 0; "
                    f"border-radius: 4px;"
                )
