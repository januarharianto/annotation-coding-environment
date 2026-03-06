"""Results step component for the manager wizard.

Handles coder package import/merge, ICR dashboard, and data export.
"""

import csv
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from nicegui import app, events, ui

from ace.models.assignment import get_assignments_for_coder
from ace.models.coder import list_coders
from ace.services.exporter import export_annotations_csv
from ace.services.icr import compute_icr
from ace.services.packager import import_coder_package


def build(conn, stepper) -> None:
    """Build the Results step UI inside the current stepper step context."""

    # ── Import section ──────────────────────────────────────────────
    ui.label("Import coder packages").classes("text-subtitle1 text-weight-medium")
    ui.label(
        "Drop returned .ace coder packages here to merge annotations back into the project."
    ).classes("text-body2 text-grey-7 q-mb-sm")

    import_results_container = ui.column().classes("full-width")

    def _handle_upload(e: events.UploadEventArguments):
        name = e.name
        suffix = Path(name).suffix.lower()
        if suffix != ".ace":
            ui.notify("Please upload an .ace coder package.", type="warning")
            return

        # Save uploaded file to temp location
        tmp_dir = Path(tempfile.mkdtemp())
        dest = tmp_dir / name
        with open(dest, "wb") as f:
            shutil.copyfileobj(e.content, f)

        # Auto-backup the main project file before merge
        project_path = app.storage.general.get("project_path", "")
        if project_path:
            proj = Path(project_path)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_name = f"{proj.stem}_backup_{timestamp}{proj.suffix}"
            backup_path = proj.parent / backup_name
            try:
                shutil.copy2(str(proj), str(backup_path))
            except Exception as exc:
                ui.notify(f"Backup failed: {exc}", type="negative")
                return

        # Import/merge
        try:
            result = import_coder_package(conn, dest)
        except Exception as exc:
            ui.notify(f"Import failed: {exc}", type="negative")
            return
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # Show results
        with import_results_container:
            with ui.card().classes("full-width q-mb-sm bg-green-1").props(
                "flat bordered"
            ):
                with ui.column().classes("q-pa-sm"):
                    ui.label(f"Imported: {name}").classes(
                        "text-body1 text-weight-medium"
                    )
                    with ui.row().classes("gap-4"):
                        ui.label(
                            f"Annotations imported: {result.annotations_imported}"
                        ).classes("text-body2")
                        ui.label(
                            f"Updated: {result.annotations_updated}"
                        ).classes("text-body2")
                        ui.label(
                            f"Skipped: {result.annotations_skipped}"
                        ).classes("text-body2")
                        ui.label(
                            f"Notes imported: {result.notes_imported}"
                        ).classes("text-body2")
                    if result.warnings:
                        ui.label("Warnings:").classes(
                            "text-body2 text-weight-medium text-warning q-mt-xs"
                        )
                        for warning in result.warnings:
                            ui.label(f"  - {warning}").classes(
                                "text-body2 text-warning"
                            )

        ui.notify(
            f"Imported {result.annotations_imported} annotations from {name}.",
            type="positive",
        )
        merge_status.refresh()

    ui.upload(
        label="Drop .ace coder packages here (or click to browse)",
        auto_upload=True,
        multiple=True,
        on_upload=_handle_upload,
    ).props('accept=".ace" flat bordered').classes("full-width")

    ui.separator().classes("q-my-md")

    # ── Merge status ────────────────────────────────────────────────
    ui.label("Merge status").classes("text-subtitle1 text-weight-medium")

    @ui.refreshable
    def merge_status():
        coders = list_coders(conn)
        if not coders:
            ui.label("No coders defined.").classes(
                "text-body2 text-grey-7 q-my-sm"
            )
            return

        columns = [
            {"name": "coder", "label": "Coder", "field": "coder", "align": "left"},
            {"name": "assigned", "label": "Assigned", "field": "assigned", "align": "center"},
            {"name": "completed", "label": "Completed", "field": "completed", "align": "center"},
            {"name": "annotations", "label": "Annotations", "field": "annotations", "align": "center"},
            {"name": "returned", "label": "Returned", "field": "returned", "align": "center"},
        ]
        rows = []
        for coder in coders:
            assignments = get_assignments_for_coder(conn, coder["id"])
            total_assigned = len(assignments)
            completed = sum(
                1 for a in assignments if a["status"] == "complete"
            )
            # Count annotations from this coder
            ann_count = conn.execute(
                "SELECT COUNT(*) FROM annotation WHERE coder_id = ? AND deleted_at IS NULL",
                (coder["id"],),
            ).fetchone()[0]
            has_returned = ann_count > 0
            rows.append(
                {
                    "coder": coder["name"],
                    "assigned": total_assigned,
                    "completed": completed,
                    "annotations": ann_count,
                    "returned": "Yes" if has_returned else "No",
                }
            )

        ui.table(columns=columns, rows=rows).classes("full-width")

    merge_status()

    ui.separator().classes("q-my-md")

    # ── ICR Dashboard ───────────────────────────────────────────────
    ui.label("Inter-coder reliability").classes("text-subtitle1 text-weight-medium")
    ui.label(
        "Compute agreement metrics across double-coded sources."
    ).classes("text-body2 text-grey-7 q-mb-sm")

    icr_container = ui.column().classes("full-width")

    # Store ICR result for export
    icr_state = {"result": None}

    async def _compute_icr():
        icr_container.clear()
        with icr_container:
            ui.spinner("dots", size="lg")

        try:
            icr_result = compute_icr(conn)
        except Exception as exc:
            icr_container.clear()
            with icr_container:
                ui.label(f"ICR computation failed: {exc}").classes(
                    "text-body2 text-negative"
                )
            return

        icr_state["result"] = icr_result

        icr_container.clear()
        with icr_container:
            if icr_result.overlap_sources == 0:
                ui.label(
                    "No overlap sources found. ICR requires at least one source assigned to two coders."
                ).classes("text-body2 text-grey-7")
                return

            # Overall metrics
            with ui.card().classes("full-width q-mb-md bg-blue-1").props(
                "flat bordered"
            ):
                with ui.row().classes("items-center gap-6 q-pa-sm"):
                    with ui.column():
                        ui.label("Overall Kappa").classes("text-caption text-grey-7")
                        ui.label(f"{icr_result.overall_kappa:.3f}").classes(
                            "text-h6 text-weight-bold"
                        )
                    with ui.column():
                        ui.label("Overall % Agreement").classes(
                            "text-caption text-grey-7"
                        )
                        ui.label(
                            f"{icr_result.overall_percent_agreement:.1%}"
                        ).classes("text-h6 text-weight-bold")
                    with ui.column():
                        ui.label("Overlap Sources").classes(
                            "text-caption text-grey-7"
                        )
                        ui.label(str(icr_result.overlap_sources)).classes(
                            "text-h6 text-weight-bold"
                        )

            # Per-code table
            columns = [
                {"name": "code", "label": "Code Name", "field": "code", "align": "left"},
                {"name": "kappa", "label": "Cohen's Kappa", "field": "kappa", "align": "center"},
                {"name": "agreement", "label": "% Agreement", "field": "agreement", "align": "center"},
                {"name": "positions", "label": "Positions Compared", "field": "positions", "align": "center"},
            ]
            rows = []
            for code_name, metrics in icr_result.per_code.items():
                kappa = metrics["kappa"]
                pct = metrics["percent_agreement"]
                rows.append(
                    {
                        "code": code_name,
                        "kappa": f"{kappa:.3f}" if kappa is not None else "N/A",
                        "agreement": f"{pct:.1%}" if pct is not None else "N/A",
                        "positions": metrics["n_positions"],
                    }
                )

            ui.table(columns=columns, rows=rows).classes("full-width")

    ui.button("Compute ICR", icon="calculate", on_click=_compute_icr).props(
        "unelevated color=primary"
    )

    ui.separator().classes("q-my-md")

    # ── Export section ──────────────────────────────────────────────
    ui.label("Export").classes("text-subtitle1 text-weight-medium")

    project_path = app.storage.general.get("project_path", "")
    default_dir = str(Path(project_path).parent) if project_path else ""

    export_path_input = ui.input(
        "Export folder",
        value=default_dir,
        placeholder="/path/to/output/folder",
    ).props("outlined dense").classes("full-width q-mb-sm")

    export_results_container = ui.column().classes("full-width")

    async def _export_csv():
        out_dir = (export_path_input.value or "").strip()
        if not out_dir:
            ui.notify("Please enter an export folder.", type="warning")
            return

        out_path = Path(out_dir)
        if not out_path.exists():
            try:
                out_path.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                ui.notify(f"Cannot create folder: {exc}", type="negative")
                return

        csv_path = out_path / "annotations.csv"
        try:
            row_count = export_annotations_csv(conn, csv_path)
        except Exception as exc:
            ui.notify(f"Export failed: {exc}", type="negative")
            return

        export_results_container.clear()
        with export_results_container:
            with ui.card().classes("full-width q-mb-sm bg-green-1").props(
                "flat bordered"
            ):
                with ui.column().classes("q-pa-sm"):
                    ui.label(
                        f"Exported {row_count} annotation(s) to:"
                    ).classes("text-body1 text-weight-medium")
                    ui.label(str(csv_path)).classes("text-body2 text-grey-7")

        ui.notify(f"Exported {row_count} annotations.", type="positive")

    async def _export_icr():
        if icr_state["result"] is None:
            ui.notify(
                "Compute ICR first before exporting.", type="warning"
            )
            return

        out_dir = (export_path_input.value or "").strip()
        if not out_dir:
            ui.notify("Please enter an export folder.", type="warning")
            return

        out_path = Path(out_dir)
        if not out_path.exists():
            try:
                out_path.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                ui.notify(f"Cannot create folder: {exc}", type="negative")
                return

        icr_path = out_path / "icr_report.csv"
        icr_result = icr_state["result"]

        try:
            with open(icr_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["Code Name", "Cohen's Kappa", "% Agreement", "Positions Compared"]
                )
                for code_name, metrics in icr_result.per_code.items():
                    kappa = metrics["kappa"]
                    pct = metrics["percent_agreement"]
                    writer.writerow(
                        [
                            code_name,
                            f"{kappa:.3f}" if kappa is not None else "",
                            f"{pct:.3f}" if pct is not None else "",
                            metrics["n_positions"],
                        ]
                    )
                # Overall row
                writer.writerow([])
                writer.writerow(
                    [
                        "Overall (macro-average)",
                        f"{icr_result.overall_kappa:.3f}",
                        f"{icr_result.overall_percent_agreement:.3f}",
                        "",
                    ]
                )
                writer.writerow(
                    ["Overlap sources", icr_result.overlap_sources, "", ""]
                )
        except Exception as exc:
            ui.notify(f"Export failed: {exc}", type="negative")
            return

        export_results_container.clear()
        with export_results_container:
            with ui.card().classes("full-width q-mb-sm bg-green-1").props(
                "flat bordered"
            ):
                with ui.column().classes("q-pa-sm"):
                    ui.label("ICR report exported to:").classes(
                        "text-body1 text-weight-medium"
                    )
                    ui.label(str(icr_path)).classes("text-body2 text-grey-7")

        ui.notify("ICR report exported.", type="positive")

    with ui.row().classes("gap-2"):
        ui.button(
            "Export annotations CSV", icon="download", on_click=_export_csv
        ).props("unelevated color=primary")
        ui.button(
            "Export ICR report", icon="assessment", on_click=_export_icr
        ).props("outline")

    # ── Navigation ──────────────────────────────────────────────────
    with ui.row().classes("q-mt-md gap-2"):
        ui.button("Back", on_click=stepper.previous).props("flat")
