"""Manager page with stepper wizard."""

from nicegui import app, ui

from ace.db.connection import checkpoint_and_close, open_project
from ace.models.project import get_project
from ace.pages.manager import import_data


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
                ui.label("Codebook configuration will go here.").classes("text-body2 text-grey-7")
                with ui.row().classes("q-mt-md gap-2"):
                    ui.button("Back", on_click=stepper.previous).props("flat")
                    ui.button("Next: Assign & Export", icon="arrow_forward", on_click=stepper.next).props("unelevated")

            with ui.step("Assign & Export"):
                ui.label("Assignment and export options will go here.").classes("text-body2 text-grey-7")
                with ui.row().classes("q-mt-md gap-2"):
                    ui.button("Back", on_click=stepper.previous).props("flat")
                    ui.button("Next: Results", icon="arrow_forward", on_click=stepper.next).props("unelevated")

            with ui.step("Results"):
                ui.label("Results and analysis will go here.").classes("text-body2 text-grey-7")
                with ui.row().classes("q-mt-md gap-2"):
                    ui.button("Back", on_click=stepper.previous).props("flat")


def _go_home(conn):
    """Return a callback that closes the connection and navigates home."""

    def handler():
        try:
            checkpoint_and_close(conn)
        except Exception:
            pass
        ui.navigate.to("/")

    return handler
