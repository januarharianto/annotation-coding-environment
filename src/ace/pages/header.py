"""Shared header bar for all ACE pages."""

import tempfile
from datetime import date
from pathlib import Path

from nicegui import app, ui

from ace.models.project import get_project
from ace.services.exporter import export_annotations_csv


def build_header(*, project_name: str | None = None, conn=None) -> None:
    """Build the shared top header bar.

    Args:
        project_name: If set, show as clickable link to home. Otherwise show "ACE" branding.
        conn: If set, show Export button and More menu (for coding page).
    """
    edit_dialog = ui.dialog()

    with ui.header().classes("bg-white text-dark items-center q-px-md").style(
        "border-bottom: 1px solid #bdbdbd; min-height: 40px; height: 40px;"
    ):
        with ui.row().classes("items-center full-width no-wrap").style("height: 100%;"):
            # Left: project name or branding
            if project_name:
                ui.button(
                    project_name,
                    icon="arrow_back",
                    on_click=lambda: ui.navigate.to("/"),
                ).props("flat dense no-caps").classes(
                    "text-subtitle2 text-weight-bold text-grey-8"
                ).tooltip("Back to home")
            else:
                ui.label("ACE").classes("text-subtitle2 text-weight-bold text-grey-8")

            ui.space()

            # Right: actions (only when conn is provided, i.e. coding page)
            if conn is not None:
                _project = get_project(conn)
                _project_name_for_file = _project["name"] if _project else "project"

                def _export():
                    tmp = tempfile.NamedTemporaryFile(
                        suffix=".csv", delete=False, prefix="ace_export_"
                    )
                    tmp.close()
                    count = export_annotations_csv(conn, tmp.name)
                    if count == 0:
                        ui.notify("No annotations to export.", type="info", position="bottom")
                        Path(tmp.name).unlink(missing_ok=True)
                        return
                    safe_name = "".join(
                        c if c.isalnum() or c in (" ", "-", "_") else "_"
                        for c in _project_name_for_file
                    )
                    filename = f"{safe_name}_export_{date.today().isoformat()}.csv"
                    ui.download(tmp.name, filename)

                ui.button("Export", icon="download", on_click=_export).props(
                    "flat dense no-caps"
                ).classes("text-grey-8")

                with ui.button(icon="more_vert").props("flat round dense").classes(
                    "text-grey-7"
                ):
                    with ui.menu():
                        ui.menu_item("Settings (coming soon)").props("disable")

            # Far right: coder name (if set)
            coder_name = app.storage.general.get("coder_name")
            if coder_name:

                def _open_edit():
                    edit_dialog.clear()
                    with edit_dialog, ui.card().classes("q-pa-md").style("min-width: 300px;"):
                        ui.label("Edit Name").classes("text-subtitle1 text-weight-medium q-mb-sm")
                        name_input = ui.input("Your name", value=coder_name).props(
                            "autofocus outlined dense"
                        )

                        def _save():
                            new_name = name_input.value.strip()
                            if not new_name:
                                return
                            app.storage.general["coder_name"] = new_name
                            edit_dialog.close()
                            ui.navigate.reload()

                        with ui.row().classes("q-mt-md justify-end full-width gap-2"):
                            ui.button("Cancel", on_click=edit_dialog.close).props("flat")
                            ui.button("Save", on_click=_save).props("unelevated color=primary")

                    edit_dialog.open()

                ui.button(coder_name, icon="edit", on_click=_open_edit).props(
                    "flat dense no-caps size=sm"
                ).classes("text-caption text-grey-7 q-ml-sm")
