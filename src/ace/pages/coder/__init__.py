"""Coder annotation page."""

from nicegui import app, ui

from ace.db.connection import open_project
from ace.pages.coder.coding import build


def register() -> None:
    """Register the /coder route."""

    @ui.page("/coder")
    def coder_page():
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
