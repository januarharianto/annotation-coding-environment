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
        with ui.row().classes("items-center full-width gap-2"):
            path_input = ui.input("Save location").props("readonly").classes("col")
            path_input.value = str(Path.home())

            async def _browse_save_location() -> None:
                current_dir = Path(path_input.value)
                with ui.dialog(value=True) as dir_dialog, ui.card().classes(
                    "q-pa-md"
                ).style("min-width: 450px; max-height: 70vh;"):
                    ui.label("Choose Save Location").classes("text-subtitle1")
                    dir_path_label = ui.label(str(current_dir)).classes(
                        "text-caption text-grey-7"
                    ).style("word-break: break-all;")
                    dir_listing = ui.column().classes("full-width").style(
                        "max-height: 350px; overflow-y: auto;"
                    )

                    def _dir_refresh() -> None:
                        nonlocal current_dir
                        dir_path_label.text = str(current_dir)
                        dir_listing.clear()
                        folders, _ = _list_dir(current_dir)
                        with dir_listing:
                            if current_dir.parent != current_dir:
                                ui.item(
                                    "..",
                                    on_click=lambda _p=current_dir.parent: _dir_nav(_p),
                                ).props("clickable").classes("text-weight-bold")
                            for folder in folders:
                                ui.item(
                                    f"\U0001F4C1  {folder.name}",
                                    on_click=lambda _f=folder: _dir_nav(_f),
                                ).props("clickable")
                            if not folders:
                                ui.label("No subfolders.").classes(
                                    "text-grey-5 q-pa-sm"
                                )

                    def _dir_nav(target: Path) -> None:
                        nonlocal current_dir
                        current_dir = target.resolve()
                        _dir_refresh()

                    def _dir_select() -> None:
                        path_input.value = str(current_dir)
                        dir_dialog.close()

                    _dir_refresh()

                    with ui.row().classes("q-mt-md justify-end full-width gap-2"):
                        ui.button("Cancel", on_click=dir_dialog.close).props("flat")
                        ui.button(
                            "Select This Folder", on_click=_dir_select
                        ).props("unelevated color=primary")

            ui.button(icon="folder_open", on_click=_browse_save_location).props(
                "flat dense"
            )

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


def _list_dir(directory: Path) -> tuple[list[Path], list[Path]]:
    """Return (sorted folders, sorted .ace files) in directory."""
    folders = []
    ace_files = []
    try:
        for entry in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                folders.append(entry)
            elif entry.suffix == ".ace":
                ace_files.append(entry)
    except PermissionError:
        pass
    return folders, ace_files


async def _open_file_picker() -> None:
    """Show a file browser dialog to find and open an .ace project."""
    current_dir = Path.home()

    with ui.dialog(value=True) as dialog, ui.card().classes("q-pa-md").style(
        "min-width: 500px; max-height: 80vh;"
    ):
        ui.label("Open Project").classes("text-h6")

        path_label = ui.label(str(current_dir)).classes(
            "text-caption text-grey-7"
        ).style("word-break: break-all;")

        listing = ui.column().classes("full-width").style(
            "max-height: 400px; overflow-y: auto;"
        )

        def _refresh() -> None:
            nonlocal current_dir
            path_label.text = str(current_dir)
            listing.clear()
            folders, ace_files = _list_dir(current_dir)

            with listing:
                # Parent directory
                if current_dir.parent != current_dir:
                    ui.item(
                        "..",
                        on_click=lambda _p=current_dir.parent: _navigate(_p),
                    ).props("clickable").classes("text-weight-bold")

                for folder in folders:
                    ui.item(
                        f"\U0001F4C1  {folder.name}",
                        on_click=lambda _f=folder: _navigate(_f),
                    ).props("clickable")

                for ace_file in ace_files:
                    ui.item(
                        f"\U0001F4C4  {ace_file.name}",
                        on_click=lambda _a=ace_file: _select(_a),
                    ).props("clickable").classes("text-primary text-weight-medium")

                if not folders and not ace_files:
                    ui.label("No folders or .ace files here.").classes(
                        "text-grey-5 q-pa-sm"
                    )

        def _navigate(target: Path) -> None:
            nonlocal current_dir
            current_dir = target.resolve()
            _refresh()

        def _select(file_path: Path) -> None:
            dialog.close()
            _store_and_route(file_path)

        _refresh()

        with ui.row().classes("q-mt-md justify-end full-width"):
            ui.button("Cancel", on_click=dialog.close).props("flat")


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
