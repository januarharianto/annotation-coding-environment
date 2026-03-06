"""Assign & Export step component for the manager wizard."""

import time
from pathlib import Path

from nicegui import app, ui

from ace.models.coder import add_coder, list_coders
from ace.models.project import get_project
from ace.models.source import list_sources
from ace.services.assigner import generate_assignments
from ace.services.packager import export_coder_package


def _assignments_exist(conn) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM assignment").fetchone()
    return row[0] > 0


def _remove_coder(conn, coder_id: str) -> None:
    conn.execute("DELETE FROM coder WHERE id = ?", (coder_id,))
    conn.commit()


def build(conn, stepper) -> None:
    """Build the Assign & Export step UI."""

    state = {
        "overlap_pct": 20,
        "seed": int(time.time()),
    }

    # ── Assign section ──────────────────────────────────────────────
    ui.label("Coders").classes("text-subtitle1 text-weight-medium")

    @ui.refreshable
    def coder_list():
        coders = list_coders(conn)
        locked = _assignments_exist(conn)

        if not coders:
            ui.label("No coders added yet.").classes(
                "text-body2 text-grey-7 q-my-sm"
            )
        else:
            for coder in coders:
                with ui.row().classes("items-center full-width q-py-xs"):
                    ui.icon("person").classes("text-grey-7")
                    ui.label(coder["name"]).classes("text-body1 col")
                    if locked:
                        btn = ui.button(icon="delete").props(
                            "flat round dense size=sm disable"
                        )
                        btn.tooltip(
                            "Cannot remove coders after assignments are generated"
                        )
                    else:
                        ui.button(
                            icon="delete",
                            on_click=lambda c=coder: _do_remove_coder(
                                conn, c, coder_list, preview_table
                            ),
                        ).props("flat round dense size=sm color=negative")

    coder_list()

    # Add coder input
    with ui.row().classes("q-mt-sm items-center gap-2"):
        coder_input = ui.input(
            "Coder name", placeholder="Enter coder name"
        ).props("outlined dense")

        def _add_coder():
            name = (coder_input.value or "").strip()
            if not name:
                ui.notify("Please enter a coder name.", type="warning")
                return
            if _assignments_exist(conn):
                ui.notify(
                    "Cannot add coders after assignments are generated.",
                    type="warning",
                )
                return
            existing = list_coders(conn)
            if any(c["name"] == name for c in existing):
                ui.notify(f"Coder '{name}' already exists.", type="warning")
                return
            try:
                add_coder(conn, name)
            except Exception as exc:
                ui.notify(f"Error: {exc}", type="negative")
                return
            ui.notify(f"Coder '{name}' added.", type="positive")
            coder_input.value = ""
            coder_list.refresh()
            preview_table.refresh()

        ui.button("Add", icon="person_add", on_click=_add_coder).props(
            "outline dense"
        )

    ui.separator().classes("q-my-md")

    # ── Overlap slider ──────────────────────────────────────────────
    ui.label("ICR overlap").classes("text-subtitle1 text-weight-medium")
    ui.label(
        "Percentage of sources coded by two coders for reliability checking."
    ).classes("text-body2 text-grey-7 q-mb-xs")

    overlap_label = ui.label(f"{state['overlap_pct']}%").classes(
        "text-h6 text-weight-bold"
    )

    def _on_overlap_change(e):
        state["overlap_pct"] = int(e.value)
        overlap_label.text = f"{int(e.value)}%"
        preview_table.refresh()

    ui.slider(
        min=0,
        max=100,
        step=1,
        value=state["overlap_pct"],
        on_change=_on_overlap_change,
    ).props("label-always").classes("q-mt-xs")

    ui.separator().classes("q-my-md")

    # ── Random seed ─────────────────────────────────────────────────
    ui.label("Random seed").classes("text-subtitle1 text-weight-medium")
    ui.label("Auto-generated for reproducibility.").classes(
        "text-body2 text-grey-7 q-mb-xs"
    )
    ui.input("Seed", value=str(state["seed"])).props(
        "outlined dense readonly"
    ).classes("q-mb-md")

    # ── Preview table ───────────────────────────────────────────────
    ui.label("Assignment preview").classes("text-subtitle1 text-weight-medium")

    @ui.refreshable
    def preview_table():
        coders = list_coders(conn)
        sources = list_sources(conn)

        if not coders or not sources:
            ui.label("Add coders and import sources to see a preview.").classes(
                "text-body2 text-grey-7 q-my-sm"
            )
            return

        if len(coders) < 2:
            ui.label(
                "Add at least 2 coders to generate assignments."
            ).classes("text-body2 text-grey-7 q-my-sm")
            return

        coder_ids = [c["id"] for c in coders]
        coder_names = {c["id"]: c["name"] for c in coders}

        try:
            preview = generate_assignments(
                conn,
                coder_ids,
                state["overlap_pct"],
                state["seed"],
                preview_only=True,
            )
        except Exception as exc:
            ui.label(f"Preview error: {exc}").classes(
                "text-body2 text-negative"
            )
            return

        # Summary card
        with ui.card().classes("full-width q-mb-sm bg-blue-1").props(
            "flat bordered"
        ):
            with ui.row().classes("items-center gap-4 q-pa-sm"):
                ui.label(f"Total sources: {preview.total_sources}").classes(
                    "text-body2"
                )
                ui.label(
                    f"Overlap sources: {preview.overlap_sources}"
                ).classes("text-body2")
                ui.label(
                    f"Unique sources: {preview.unique_sources}"
                ).classes("text-body2")

        # Per-coder table
        columns = [
            {
                "name": "coder",
                "label": "Coder",
                "field": "coder",
                "align": "left",
            },
            {
                "name": "unique",
                "label": "Unique",
                "field": "unique",
                "align": "center",
            },
            {
                "name": "overlap",
                "label": "Overlap",
                "field": "overlap",
                "align": "center",
            },
            {
                "name": "total",
                "label": "Total workload",
                "field": "total",
                "align": "center",
            },
        ]
        rows = []
        for cid, stats in preview.per_coder.items():
            rows.append(
                {
                    "coder": coder_names.get(cid, cid),
                    "unique": stats["unique"],
                    "overlap": stats["overlap"],
                    "total": stats["total"],
                }
            )
        ui.table(columns=columns, rows=rows).classes("full-width")

    preview_table()

    ui.separator().classes("q-my-md")

    # ── Generate button ─────────────────────────────────────────────

    @ui.refreshable
    def generate_section():
        locked = _assignments_exist(conn)

        if locked:
            with ui.card().classes("full-width q-mb-md bg-green-1").props(
                "flat bordered"
            ):
                ui.label(
                    "Assignments have been generated. Export coder packages below."
                ).classes("text-body2 text-weight-medium q-pa-sm")
        else:

            def _open_confirm_dialog():
                coders = list_coders(conn)
                sources = list_sources(conn)

                if len(coders) < 2:
                    ui.notify(
                        "Add at least 2 coders.", type="warning"
                    )
                    return
                if not sources:
                    ui.notify("Import sources first.", type="warning")
                    return

                coder_ids = [c["id"] for c in coders]
                preview = generate_assignments(
                    conn,
                    coder_ids,
                    state["overlap_pct"],
                    state["seed"],
                    preview_only=True,
                )

                avg_workload = 0
                if preview.per_coder:
                    avg_workload = round(
                        sum(s["total"] for s in preview.per_coder.values())
                        / len(preview.per_coder)
                    )

                with ui.dialog() as dialog, ui.card().classes(
                    "q-pa-md"
                ).style("min-width: 450px"):
                    ui.label("Confirm assignments").classes(
                        "text-h6 q-mb-md"
                    )
                    ui.label(
                        f"You are about to create {len(coders)} coder packages. "
                        f"Each coder will receive approximately {avg_workload} documents. "
                        f"{preview.overlap_sources} documents will be coded by 2 coders "
                        f"for reliability checking."
                    ).classes("text-body1 q-mb-sm")
                    ui.label(
                        "This cannot be changed after export."
                    ).classes("text-body2 text-weight-bold text-negative")

                    with ui.row().classes("q-mt-md justify-end gap-2"):
                        ui.button("Cancel", on_click=dialog.close).props(
                            "flat"
                        )

                        def _do_generate():
                            try:
                                generate_assignments(
                                    conn,
                                    coder_ids,
                                    state["overlap_pct"],
                                    state["seed"],
                                    preview_only=False,
                                )
                            except Exception as exc:
                                ui.notify(
                                    f"Error: {exc}", type="negative"
                                )
                                return
                            ui.notify(
                                "Assignments generated successfully.",
                                type="positive",
                            )
                            dialog.close()
                            generate_section.refresh()
                            export_section.refresh()

                        ui.button(
                            "Generate",
                            icon="assignment",
                            on_click=_do_generate,
                        ).props("unelevated color=primary")

                dialog.open()

            ui.button(
                "Generate assignments",
                icon="assignment",
                on_click=_open_confirm_dialog,
            ).props("unelevated color=primary")

    generate_section()

    ui.separator().classes("q-my-md")

    # ── Export section ──────────────────────────────────────────────
    ui.label("Export").classes("text-subtitle1 text-weight-medium")

    @ui.refreshable
    def export_section():
        if not _assignments_exist(conn):
            ui.label(
                "Generate assignments first to enable export."
            ).classes("text-body2 text-grey-7 q-my-sm")
            return

        project_path = app.storage.general.get("project_path", "")
        default_dir = str(Path(project_path).parent) if project_path else ""

        output_input = ui.input(
            "Export folder",
            value=default_dir,
            placeholder="/path/to/output/folder",
        ).props("outlined dense").classes("full-width q-mb-sm")

        results_container = ui.column().classes("full-width")

        async def _do_export():
            out_dir = (output_input.value or "").strip()
            if not out_dir:
                ui.notify("Please enter an output folder.", type="warning")
                return

            out_path = Path(out_dir)
            if not out_path.exists():
                try:
                    out_path.mkdir(parents=True, exist_ok=True)
                except Exception as exc:
                    ui.notify(f"Cannot create folder: {exc}", type="negative")
                    return

            coders = list_coders(conn)
            if not coders:
                ui.notify("No coders found.", type="warning")
                return

            results_container.clear()
            with results_container:
                spinner = ui.spinner("dots", size="lg")

            exported_paths = []
            errors = []

            for coder in coders:
                try:
                    pkg_path = export_coder_package(
                        conn, coder["id"], out_dir
                    )
                    exported_paths.append((coder["name"], str(pkg_path)))
                except Exception as exc:
                    errors.append((coder["name"], str(exc)))

            results_container.clear()
            with results_container:
                if exported_paths:
                    ui.label(
                        f"Exported {len(exported_paths)} coder package(s)."
                    ).classes("text-body1 text-weight-medium text-positive")

                    columns = [
                        {
                            "name": "coder",
                            "label": "Coder",
                            "field": "coder",
                            "align": "left",
                        },
                        {
                            "name": "path",
                            "label": "File path",
                            "field": "path",
                            "align": "left",
                        },
                    ]
                    rows = [
                        {"coder": name, "path": path}
                        for name, path in exported_paths
                    ]
                    ui.table(columns=columns, rows=rows).classes("full-width")

                if errors:
                    ui.label("Errors:").classes(
                        "text-body1 text-weight-medium text-negative q-mt-sm"
                    )
                    for name, err in errors:
                        ui.label(f"{name}: {err}").classes(
                            "text-body2 text-negative"
                        )

        ui.button(
            "Export coder packages", icon="download", on_click=_do_export
        ).props("unelevated color=primary")

    export_section()

    # ── Navigation ──────────────────────────────────────────────────
    with ui.row().classes("q-mt-md gap-2"):
        ui.button("Back", on_click=stepper.previous).props("flat")
        ui.button(
            "Next: Results", icon="arrow_forward", on_click=stepper.next
        ).props("unelevated")


def _do_remove_coder(conn, coder, coder_list_refreshable, preview_refreshable):
    _remove_coder(conn, coder["id"])
    ui.notify(f"Coder '{coder['name']}' removed.", type="positive")
    coder_list_refreshable.refresh()
    preview_refreshable.refresh()
