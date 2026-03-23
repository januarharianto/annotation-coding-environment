"""Landing page for ACE."""

import asyncio
import platform
import subprocess
from pathlib import Path

from nicegui import app, ui

from ace.pages.header import build_header
from ace.db.connection import (
    checkpoint_and_close,
    create_project,
    open_project,
)
from ace.models.source import list_sources
from ace.services.cloud_detect import is_cloud_sync_path


def _update_recent(file_path: Path) -> None:
    """Add file_path to the recent files list (most recent first, max 3)."""
    str_path = str(file_path)
    app.storage.general["project_path"] = str_path
    recents = list(app.storage.general.get("recent_files", []))
    if str_path in recents:
        recents.remove(str_path)
    recents.insert(0, str_path)
    app.storage.general["recent_files"] = recents[:3]


def _store_and_route(file_path: Path) -> None:
    """Open a project file, store its path, and navigate to the correct route."""
    try:
        conn = open_project(file_path)
    except (ValueError, FileNotFoundError) as exc:
        ui.notify(str(exc), type="negative")
        return

    sources = list_sources(conn)
    conn.close()

    _update_recent(file_path)

    if is_cloud_sync_path(file_path):
        ui.notify(
            "Warning: This file is in a cloud-sync folder (Dropbox, OneDrive, iCloud, or Google Drive). "
            "SQLite WAL files may not sync correctly. Consider moving the .ace file to a local directory.",
            type="warning",
            timeout=10000,
        )

    if sources:
        ui.navigate.to("/code")
    else:
        ui.navigate.to("/import")


def _ask_overwrite(file_path: Path, on_confirm) -> None:
    """Show a confirmation dialog to overwrite an existing .ace file."""
    with ui.dialog(value=True) as dlg, ui.card().classes("q-pa-md"):
        ui.label(f'"{file_path.name}" already exists.').classes("text-body1")
        ui.label("Overwrite it? All existing data will be lost.").classes(
            "text-body2 text-grey-8"
        )
        with ui.row().classes("q-mt-md justify-end full-width gap-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")

            def _confirm():
                dlg.close()
                on_confirm(overwrite=True)

            ui.button("Overwrite", on_click=_confirm).props(
                "unelevated color=negative"
            )


def register() -> None:
    """Register the landing page route."""

    @ui.page("/")
    def landing():
        build_header()

        with ui.column().classes("absolute-center items-center gap-6"):
            ui.label("ACE").classes("text-h3 text-weight-bold")
            ui.label("Annotation Coding Environment").classes(
                "text-subtitle1 text-grey-8"
            )

            # First-time name input (collapses once saved)
            if not app.storage.general.get("coder_name"):
                with ui.column().classes("items-center gap-2 q-mt-sm").style("width: 280px;"):
                    ui.label("What's your name?").classes("text-body2 text-grey-7")
                    _name_input = ui.input(placeholder="Your name").props(
                        "autofocus outlined dense"
                    ).classes("full-width")

                    def _save_name():
                        name = _name_input.value.strip()
                        if not name:
                            return
                        app.storage.general["coder_name"] = name
                        ui.navigate.reload()

                    _name_input.on("keydown.enter", lambda: _save_name())
                    ui.button("Save", on_click=_save_name).props(
                        "unelevated color=primary dense"
                    ).classes("full-width")

            # Resume button if there's an active project with sources
            current = app.storage.general.get("project_path")
            if current and Path(current).is_file():
                try:
                    _conn = open_project(current)
                    _has_sources = bool(list_sources(_conn))
                    _conn.close()
                except (ValueError, FileNotFoundError):
                    _has_sources = False
                if _has_sources:
                    ui.button(
                        "Resume Coding",
                        icon="play_arrow",
                        on_click=lambda: ui.navigate.to("/code"),
                    ).props("unelevated color=primary").classes("q-mt-md").style("min-width: 200px;")

            with ui.row().classes("gap-4 q-mt-md"):
                ui.button("New Project", icon="add", on_click=_open_new_dialog).props(
                    "unelevated"
                )
                ui.button(
                    "Open Project", icon="folder_open", on_click=_open_file_picker
                ).props("outline")
                ui.button(
                    "Check Agreement",
                    icon="compare_arrows",
                    on_click=lambda: ui.navigate.to("/agreement"),
                ).props("outline")

            # Recent files
            recents: list = app.storage.general.get("recent_files", [])
            # Filter to files that still exist
            recents = [r for r in recents if Path(r).is_file()]
            if recents:
                ui.separator().classes("q-my-sm").style("width: 300px")
                with ui.row().classes("items-center full-width justify-between").style("width: 300px"):
                    ui.label("Recent").classes("text-caption text-grey-7")

                    def _clear_recents():
                        app.storage.general["recent_files"] = []
                        ui.navigate.reload()

                    ui.button("Clear", on_click=_clear_recents).props(
                        "flat dense no-caps"
                    ).classes("text-caption text-grey-7")
                with ui.column().classes("gap-0").style("width: 300px"):
                    for rpath in recents:
                        p = Path(rpath)

                        def _open_recent(_e, fp=p):
                            _store_and_route(fp)

                        with ui.row().classes(
                            "items-center full-width cursor-pointer q-py-xs q-px-sm ace-recent-item"
                        ).style(
                            "gap: 8px; border-radius: 4px;"
                        ).on("click", _open_recent):
                            ui.icon("description", size="xs").classes("text-grey-7")
                            with ui.column().classes("gap-0").style("min-width: 0;"):
                                ui.label(p.stem).classes("text-body2 ellipsis")
                                ui.label(str(p.parent)).classes(
                                    "text-caption text-grey-7 ellipsis"
                                )


async def _open_new_dialog() -> None:
    """Show a dialog to create a new project."""
    with ui.dialog() as dialog, ui.card().classes("q-pa-md").style(
        "min-width: 380px;"
    ):
        ui.label("New Project").classes("text-subtitle1 text-weight-medium q-mb-sm")
        name_input = ui.input(placeholder="Project name").props("outlined dense").classes("full-width")
        desc_input = ui.input(placeholder="Description (optional)").props("outlined dense").classes("full-width q-mt-xs")
        path_input = ui.input(placeholder="Save location").props(
            "outlined dense readonly"
        ).classes("full-width q-mt-xs cursor-pointer ace-solid-readonly")

        async def _browse_save_location() -> None:
            if not _IS_MACOS:
                ui.notify("Folder browser not supported on this platform.", type="warning")
                return
            loop = asyncio.get_event_loop()
            chosen = await loop.run_in_executor(None, _native_pick_folder)
            if chosen:
                path_input.value = chosen.rstrip("/")

        path_input.on("click", _browse_save_location)

        error_label = ui.label("").classes("text-negative text-caption q-mt-xs")

        with ui.row().classes("q-mt-sm justify-end full-width gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")

            async def _create() -> None:
                name = name_input.value.strip()
                if not name:
                    error_label.text = "Project name is required."
                    return

                raw_path = path_input.value.strip()
                if not raw_path:
                    error_label.text = "Please choose a save location."
                    return
                save_dir = Path(raw_path)
                if not save_dir.is_dir():
                    error_label.text = "Save location is not a valid directory."
                    return

                safe_name = "".join(
                    c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name
                )
                file_path = save_dir / f"{safe_name}.ace"

                def _do_create(overwrite: bool = False) -> None:
                    nonlocal file_path
                    if overwrite and file_path.exists():
                        file_path.unlink()
                    try:
                        conn = create_project(file_path, name, desc_input.value.strip() or None)
                        checkpoint_and_close(conn)
                    except FileExistsError:
                        _ask_overwrite(file_path, _do_create)
                        return
                    except Exception as exc:
                        error_label.text = str(exc)
                        return

                    _update_recent(file_path)
                    dialog.close()
                    ui.navigate.to("/import")

                _do_create()

            ui.button("Create", on_click=_create).props("unelevated color=primary no-caps")

    dialog.open()


def _native_pick_file() -> str | None:
    """Open native macOS file picker for .ace files. Returns path or None."""
    result = subprocess.run(
        ["osascript", "-e",
         'POSIX path of (choose file of type {"ace"} with prompt "Open ACE Project")'],
        capture_output=True, text=True,
    )
    path = result.stdout.strip()
    return path if result.returncode == 0 and path else None


def _native_pick_folder(initial: str | None = None) -> str | None:
    """Open native macOS folder picker. Returns path or None."""
    script = 'POSIX path of (choose folder with prompt "Choose Save Location")'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True,
    )
    path = result.stdout.strip()
    return path if result.returncode == 0 and path else None


_IS_MACOS = platform.system() == "Darwin"


async def _open_file_picker() -> None:
    """Open a native file picker to find and open an .ace project."""
    if not _IS_MACOS:
        ui.notify("File browser not supported on this platform.", type="warning")
        return
    loop = asyncio.get_event_loop()
    chosen = await loop.run_in_executor(None, _native_pick_file)
    if chosen:
        _store_and_route(Path(chosen))


