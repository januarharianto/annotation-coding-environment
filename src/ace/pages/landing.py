"""Landing page for ACE."""

import tempfile
from pathlib import Path

from nicegui import app, events, ui

from ace.db.connection import (
    checkpoint_and_close,
    create_project,
    open_project,
)
from ace.models.project import get_project
from ace.services.cloud_detect import is_cloud_sync_path


def _store_and_route(file_path: Path) -> None:
    """Open a project file, store its path, and navigate to the correct route."""
    try:
        conn = open_project(file_path)
    except (ValueError, FileNotFoundError) as exc:
        ui.notify(str(exc), type="negative")
        return

    project = get_project(conn)
    role = project["file_role"]
    checkpoint_and_close(conn)

    app.storage.general["project_path"] = str(file_path)

    if is_cloud_sync_path(file_path):
        ui.notify(
            "Warning: This file is in a cloud-sync folder (Dropbox, OneDrive, iCloud, or Google Drive). "
            "SQLite WAL files may not sync correctly. Consider moving the .ace file to a local directory.",
            type="warning",
            timeout=10000,
        )

    if role == "manager":
        ui.navigate.to("/manager")
    elif role == "coder":
        ui.navigate.to("/coder")
    else:
        ui.notify(f"Unknown file_role: {role}", type="negative")


def register() -> None:
    """Register the landing page route."""

    @ui.page("/")
    def landing():
        with ui.column().classes("absolute-center items-center gap-6"):
            ui.label("ACE").classes("text-h3 text-weight-bold")
            ui.label("Annotation Coding Environment").classes(
                "text-subtitle1 text-grey-7"
            )

            with ui.row().classes("gap-4 q-mt-md"):
                ui.button("New Project", icon="add", on_click=_open_new_dialog).props(
                    "unelevated"
                )
                ui.button(
                    "Open Project", icon="folder_open", on_click=_open_file_picker
                ).props("outline")

            ui.separator().classes("q-my-sm").style("width: 300px")

            ui.label("or drop an .ace file below").classes("text-caption text-grey-6")
            ui.upload(
                label="Drop .ace file here",
                auto_upload=True,
                on_upload=_handle_upload,
            ).props('accept=".ace" flat bordered').classes("q-mt-xs").style(
                "width: 300px"
            )


async def _open_new_dialog() -> None:
    """Show a dialog to create a new project."""
    with ui.dialog() as dialog, ui.card().classes("q-pa-md").style("min-width: 350px"):
        ui.label("New Project").classes("text-h6")
        name_input = ui.input("Project name").props("autofocus")
        desc_input = ui.input("Description (optional)")
        path_input = ui.input("Save location").props("readonly")
        path_input.value = str(Path.home())

        error_label = ui.label("").classes("text-negative text-caption")

        with ui.row().classes("q-mt-md justify-end full-width gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            async def _create() -> None:
                name = name_input.value.strip()
                if not name:
                    error_label.text = "Project name is required."
                    return

                save_dir = Path(path_input.value.strip())
                if not save_dir.is_dir():
                    error_label.text = "Save location is not a valid directory."
                    return

                safe_name = "".join(
                    c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name
                )
                file_path = save_dir / f"{safe_name}.ace"

                try:
                    conn = create_project(file_path, name, desc_input.value.strip() or None)
                    checkpoint_and_close(conn)
                except FileExistsError:
                    error_label.text = f"File already exists: {file_path.name}"
                    return
                except Exception as exc:
                    error_label.text = str(exc)
                    return

                app.storage.general["project_path"] = str(file_path)
                dialog.close()
                ui.navigate.to("/manager")

            ui.button("Create", on_click=_create).props("unelevated color=primary")

    dialog.open()


async def _open_file_picker() -> None:
    """Show a dialog for the user to type a file path to open."""
    with ui.dialog() as dialog, ui.card().classes("q-pa-md").style("min-width: 400px"):
        ui.label("Open Project").classes("text-h6")
        path_input = ui.input(
            "Path to .ace file",
            placeholder=str(Path.home() / "project.ace"),
        ).props("autofocus").classes("full-width")

        error_label = ui.label("").classes("text-negative text-caption")

        with ui.row().classes("q-mt-md justify-end full-width gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            async def _open() -> None:
                raw = path_input.value.strip()
                if not raw:
                    error_label.text = "Please enter a file path."
                    return

                file_path = Path(raw).expanduser().resolve()
                if not file_path.exists():
                    error_label.text = "File not found."
                    return
                if file_path.suffix != ".ace":
                    error_label.text = "File must have .ace extension."
                    return

                dialog.close()
                _store_and_route(file_path)

            ui.button("Open", on_click=_open).props("unelevated color=primary")

    dialog.open()


async def _handle_upload(e: events.UploadEventArguments) -> None:
    """Handle drag-and-drop upload of an .ace file."""
    if not e.file.name.endswith(".ace"):
        ui.notify("Please upload an .ace file.", type="warning")
        return

    tmp_dir = Path(tempfile.mkdtemp())
    dest = tmp_dir / e.file.name
    content = await e.file.read()
    dest.write_bytes(content)

    _store_and_route(dest)
