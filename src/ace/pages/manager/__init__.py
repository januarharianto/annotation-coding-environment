"""Manager page with stepper wizard."""

from nicegui import app, ui

from ace.db.connection import checkpoint_and_close, open_project
from ace.models.project import get_project
from ace.pages.manager import assign, codebook, import_data, results


def register() -> None:
    """Register the /manager route."""

    @ui.page("/manager")
    def manager_page():
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

        project = get_project(conn)
        project_name = project["name"] if project else "Untitled"

        # -- Page header --
        with ui.row().classes("items-center full-width q-pa-md"):
            ui.button(icon="arrow_back", on_click=_go_home(conn)).props("flat round")
            ui.label(project_name).classes("text-h5 text-weight-medium q-ml-sm")
            ui.label("Manager").classes("text-subtitle1 text-grey-6 q-ml-sm")

        ui.separator()

        # -- Stepper wizard --
        with ui.stepper().props("vertical").classes("full-width q-pa-md") as stepper:
            with ui.step("Import"):
                import_data.build(conn, stepper)

            with ui.step("Codebook"):
                codebook.build(conn, stepper)

            with ui.step("Assign & Export"):
                assign.build(conn, stepper)

            with ui.step("Results"):
                results.build(conn, stepper)


def _go_home(conn):
    """Return a callback that closes the connection and navigates home."""

    def handler():
        try:
            checkpoint_and_close(conn)
        except Exception:
            pass
        ui.navigate.to("/")

    return handler
