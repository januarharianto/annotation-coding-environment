"""Agreement dashboard page — /agreement route."""

import platform
import subprocess
from pathlib import Path

from nicegui import ui

from ace.pages.header import build_header
from ace.services.agreement_loader import AgreementLoader


def register():
    @ui.page("/agreement")
    async def agreement_page():
        build_header()
        ui.add_css((Path(__file__).parent.parent / "static" / "css" / "agreement.css").read_text())

        loader = AgreementLoader()
        file_list_container = ui.column()
        validation_container = ui.column()
        results_container = ui.column().classes("full-width")

        with ui.column().classes("mx-auto q-pa-lg").style("max-width: 1100px; width: 100%;"):
            # Setup area
            with ui.column().classes("full-width q-mb-lg"):
                ui.label("Inter-Coder Agreement").classes("text-h5 text-weight-medium")

                # Empty state
                with ui.column().classes("items-center q-pa-xl full-width") as empty_state:
                    ui.icon("compare_arrows", size="48px", color="grey-4")
                    ui.label("Compare Coder Annotations").classes(
                        "text-h6 text-grey-5 q-mt-sm"
                    )
                    ui.label(
                        "Add two or more .ace project files to compare annotations "
                        "and compute agreement metrics."
                    ).classes("text-body2 text-grey-6").style(
                        "max-width: 400px; text-align: center;"
                    )

                # File controls
                with ui.row().classes("items-center gap-2 q-mt-md"):
                    ui.button(
                        "Add File", icon="add", on_click=lambda: _pick_and_add_file(loader, file_list_container, validation_container, compute_btn, empty_state)
                    ).props("flat dense no-caps").classes("text-grey-8")

                file_list_container.move(target_index=-1)
                validation_container.move(target_index=-1)

                compute_btn = ui.button(
                    "Compute Agreement",
                    icon="calculate",
                    on_click=lambda: _run_computation(loader, results_container),
                ).props("no-caps").classes("q-mt-md")
                compute_btn.set_visibility(False)

            results_container.move(target_index=-1)


_IS_MACOS = platform.system() == "Darwin"


async def _pick_and_add_file(loader, file_list_container, validation_container, compute_btn, empty_state):
    """Open native file picker and add the selected .ace file."""
    if _IS_MACOS:
        path = await _native_pick_files()
    else:
        ui.notify("File picker not yet supported on this platform.", type="warning")
        return

    if not path:
        return

    for p in path:
        info = loader.add_file(Path(p))

        if info.get("error"):
            ui.notify(info["error"], type="negative")
            continue

        for w in info.get("warnings", []):
            ui.notify(w, type="warning")

        with file_list_container:
            with ui.row().classes("items-center gap-2 q-pa-sm").style(
                "border: 1px solid #d0d0d0; border-radius: 0;"
            ):
                ui.icon("description", color="grey-6")
                with ui.column().classes("gap-0"):
                    ui.label(", ".join(info["coder_names"])).classes(
                        "text-subtitle2 text-weight-medium"
                    )
                    ui.label(
                        f"{info['filename']} — {info['source_count']} sources, "
                        f"{info['annotation_count']} annotations"
                    ).classes("text-caption text-grey-6")

    # Update validation
    if loader.file_count >= 2:
        empty_state.set_visibility(False)
        validation = loader.validate()
        validation_container.clear()
        with validation_container:
            for w in validation.get("warnings", []):
                with ui.row().classes("items-center gap-1"):
                    ui.icon("warning", color="orange", size="xs")
                    ui.label(w).classes("text-caption text-orange-8")

            if validation["valid"]:
                with ui.row().classes("items-center gap-1"):
                    ui.icon("check_circle", color="green", size="xs")
                    ui.label(
                        f"{validation['matched_sources']} sources, "
                        f"{validation['matched_codes']} codes matched — "
                        f"Coders: {', '.join(validation['coders'])}"
                    ).classes("text-caption text-green-8")
                compute_btn.set_visibility(True)
            else:
                with ui.row().classes("items-center gap-1"):
                    ui.icon("error", color="red", size="xs")
                    ui.label(validation["error"]).classes("text-caption text-red-8")
                compute_btn.set_visibility(False)
    elif loader.file_count == 1:
        empty_state.set_visibility(False)


async def _run_computation(loader, results_container):
    """Compute agreement metrics and render dashboard."""
    from ace.services.agreement_computer import compute_agreement

    try:
        ds = loader.build_dataset()
    except ValueError as e:
        ui.notify(str(e), type="negative")
        return

    ui.notify("Computing agreement metrics...", type="info")
    result = compute_agreement(ds)

    results_container.clear()
    with results_container:
        _render_dashboard(result, ds)


def _render_dashboard(result, dataset):
    """Render the full agreement dashboard."""
    # Tabs
    with ui.tabs().classes("text-grey-7") as tabs:
        overview_tab = ui.tab("Overview")
        if result.n_coders > 2:
            pairwise_tab = ui.tab("Pairwise")
        source_tab = ui.tab("Per Source")

    with ui.tab_panels(tabs, value=overview_tab).classes("full-width"):
        with ui.tab_panel(overview_tab):
            _render_overview(result, dataset)
        if result.n_coders > 2:
            with ui.tab_panel(pairwise_tab):
                _render_pairwise(result, dataset)
        with ui.tab_panel(source_tab):
            _render_per_source(result)


def _render_overview(result, dataset):
    """Render the Overview tab."""
    # Hero card — Krippendorff's alpha
    with ui.card().classes("full-width q-pa-lg").style("border: 1px solid #d0d0d0;"):
        ui.label("Krippendorff's Alpha").classes("text-caption text-grey-6")
        alpha_val = result.overall.krippendorffs_alpha
        alpha_str = f"{alpha_val:.3f}" if alpha_val is not None else "N/A"
        ui.label(alpha_str).classes("ace-metric-hero")
        label = _agreement_label(alpha_val)
        ui.label(label).classes("text-subtitle1 text-grey-7")

    # Secondary cards
    with ui.row().classes("gap-4 q-mt-md full-width"):
        # Kappa card
        with ui.card().classes("col q-pa-md").style("border: 1px solid #d0d0d0;"):
            if result.n_coders == 2:
                ui.label("Cohen's Kappa").classes("text-caption text-grey-6")
                val = result.overall.cohens_kappa
            else:
                ui.label("Fleiss' Kappa").classes("text-caption text-grey-6")
                val = result.overall.fleiss_kappa
            val_str = f"{val:.3f}" if val is not None else "N/A"
            ui.label(val_str).classes("ace-metric text-h5")

        # Percent agreement card
        with ui.card().classes("col q-pa-md").style("border: 1px solid #d0d0d0;"):
            ui.label("Percent Agreement").classes("text-caption text-grey-6")
            pct_str = f"{result.overall.percent_agreement:.1%}"
            ui.label(pct_str).classes("ace-metric text-h5")

    # Metadata
    ui.label(
        f"Computed across {result.n_sources} sources, "
        f"{result.n_codes} codes, {result.n_coders} coders"
    ).classes("text-caption text-grey-6 q-mt-sm")

    # Per-code table
    _render_per_code_table(result, dataset)

    # Methods paragraph button
    ui.button(
        "Copy Methods Paragraph",
        icon="content_copy",
        on_click=lambda: _copy_methods_paragraph(result),
    ).props("flat dense no-caps").classes("text-grey-8 q-mt-md")


def _render_per_code_table(result, dataset):
    """Render the per-code agreement table with toggleable additional metrics."""
    base_columns = [
        {"name": "code", "label": "Code Name", "field": "code", "sortable": True, "align": "left"},
        {"name": "pct", "label": "% Agreement", "field": "pct", "sortable": True},
        {"name": "alpha", "label": "K. Alpha", "field": "alpha", "sortable": True},
        {"name": "kappa", "label": "Kappa", "field": "kappa", "sortable": True},
    ]
    extra_columns = [
        {"name": "ac1", "label": "AC1", "field": "ac1", "sortable": True},
        {"name": "bp", "label": "B-P", "field": "bp", "sortable": True},
        {"name": "conger", "label": "Conger", "field": "conger", "sortable": True},
        {"name": "fleiss", "label": "Fleiss", "field": "fleiss", "sortable": True},
    ]

    rows = []
    for code_name, metrics in result.per_code.items():
        kappa_val = metrics.cohens_kappa if result.n_coders == 2 else metrics.fleiss_kappa
        rows.append({
            "code": code_name,
            "pct": f"{metrics.percent_agreement:.1%}",
            "alpha": f"{metrics.krippendorffs_alpha:.3f}" if metrics.krippendorffs_alpha is not None else "N/A",
            "kappa": f"{kappa_val:.3f}" if kappa_val is not None else "N/A",
            "ac1": f"{metrics.gwets_ac1:.3f}" if metrics.gwets_ac1 is not None else "N/A",
            "bp": f"{metrics.brennan_prediger:.3f}" if metrics.brennan_prediger is not None else "N/A",
            "conger": f"{metrics.congers_kappa:.3f}" if metrics.congers_kappa is not None else "N/A",
            "fleiss": f"{metrics.fleiss_kappa:.3f}" if metrics.fleiss_kappa is not None else "N/A",
            "_low": metrics.krippendorffs_alpha is not None and metrics.krippendorffs_alpha < 0.67,
        })

    with ui.row().classes("items-center justify-between full-width q-mt-lg q-mb-sm"):
        ui.label("Agreement by Code").classes("text-h6 text-weight-medium")
        with ui.row().classes("items-center gap-2"):
            ui.switch("Show all metrics", on_change=lambda e: toggle_columns(e.value))
            ui.button(
                "Export CSV",
                icon="download",
                on_click=lambda: _export_per_code_csv(result),
            ).props("flat dense no-caps").classes("text-grey-8")

    table = ui.table(columns=base_columns, rows=rows, row_key="code").props("flat dense").classes("full-width")

    def toggle_columns(show_all: bool):
        if show_all:
            table._props["columns"] = base_columns + extra_columns
        else:
            table._props["columns"] = base_columns
        table.update()


def _render_pairwise(result, dataset):
    """Render the pairwise heatmap tab."""
    coders = dataset.coders
    n = len(coders)

    # Build matrix
    matrix = [[None] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0
        for j in range(i + 1, n):
            key = (coders[i].id, coders[j].id)
            alt_key = (coders[j].id, coders[i].id)
            val = result.pairwise.get(key) or result.pairwise.get(alt_key)
            matrix[i][j] = val
            matrix[j][i] = val

    # Generate HTML
    html = '<table class="ace-heatmap"><tr><th></th>'
    for c in coders:
        html += f"<th>{c.label}</th>"
    html += "</tr>"

    for i, coder in enumerate(coders):
        html += f"<tr><th>{coder.label}</th>"
        for j in range(n):
            val = matrix[i][j]
            if val is None:
                html += "<td>—</td>"
            else:
                bg = _heatmap_color(val)
                text_color = "#ffffff" if val > 0.6 else "#212121"
                css_class = ' class="ace-low-agreement"' if val < 0.67 else ""
                html += (
                    f'<td style="background-color: {bg}; color: {text_color};"{css_class}>'
                    f"{val:.3f}</td>"
                )
        html += "</tr>"

    html += "</table>"
    ui.html(html, sanitize=False)


def _heatmap_color(value: float) -> str:
    """Interpolate from white (#ffffff) to blue (#1565c0) based on value 0-1."""
    r = int(255 + (21 - 255) * value)
    g = int(255 + (101 - 255) * value)
    b = int(255 + (192 - 255) * value)
    return f"rgb({r},{g},{b})"


def _render_per_source(result):
    """Render the per-source tab."""
    with ui.row().classes("items-center justify-between full-width q-mb-sm"):
        ui.label("Agreement by Source").classes("text-h6 text-weight-medium")
        ui.button(
            "Export CSV",
            icon="download",
            on_click=lambda: _export_per_source_csv(result),
        ).props("flat dense no-caps").classes("text-grey-8")

    columns = [
        {"name": "source", "label": "Source ID", "field": "source", "sortable": True, "align": "left"},
        {"name": "pct", "label": "% Agreement", "field": "pct", "sortable": True},
        {"name": "alpha", "label": "K. Alpha", "field": "alpha", "sortable": True},
        {"name": "kappa", "label": "Kappa", "field": "kappa", "sortable": True},
        {"name": "n_pos", "label": "Positions", "field": "n_pos", "sortable": True},
    ]

    rows = []
    for src_id, metrics in sorted(
        result.per_source.items(),
        key=lambda x: x[1].percent_agreement,
    ):
        kappa_val = metrics.cohens_kappa if result.n_coders == 2 else metrics.fleiss_kappa
        rows.append({
            "source": src_id,
            "pct": f"{metrics.percent_agreement:.1%}",
            "alpha": f"{metrics.krippendorffs_alpha:.3f}" if metrics.krippendorffs_alpha is not None else "N/A",
            "kappa": f"{kappa_val:.3f}" if kappa_val is not None else "N/A",
            "n_pos": metrics.n_positions,
        })

    ui.table(columns=columns, rows=rows, row_key="source").props("flat dense").classes("full-width")


def _agreement_label(value: float | None) -> str:
    """Return verbal agreement label (Landis & Koch scale)."""
    if value is None:
        return ""
    if value < 0.0:
        return "Poor"
    if value <= 0.20:
        return "Slight"
    if value <= 0.40:
        return "Fair"
    if value <= 0.60:
        return "Moderate"
    if value <= 0.80:
        return "Substantial"
    return "Almost Perfect"


async def _copy_methods_paragraph(result):
    """Copy a publication-ready methods paragraph to clipboard."""
    alpha = result.overall.krippendorffs_alpha
    alpha_str = f"{alpha:.2f}" if alpha is not None else "N/A"

    if result.n_coders == 2:
        kappa = result.overall.cohens_kappa
        kappa_label = "Cohen's kappa"
    else:
        kappa = result.overall.fleiss_kappa
        kappa_label = "Fleiss' kappa"
    kappa_str = f"{kappa:.2f}" if kappa is not None else "N/A"

    # Per-code range
    code_kappas = []
    for m in result.per_code.values():
        k = m.cohens_kappa if result.n_coders == 2 else m.fleiss_kappa
        if k is not None:
            code_kappas.append(k)

    range_str = ""
    if code_kappas:
        range_str = (
            f" Per-code agreement ranged from "
            f"\u03BA = {min(code_kappas):.2f} to \u03BA = {max(code_kappas):.2f}."
        )

    para = (
        f"Inter-coder reliability was assessed using Krippendorff's alpha "
        f"(\u03B1 = {alpha_str}) and {kappa_label} "
        f"(\u03BA = {kappa_str}) across {result.n_coders} coders "
        f"and {result.n_sources} source texts.{range_str}"
    )

    import json
    await ui.run_javascript(
        f"navigator.clipboard.writeText({json.dumps(para)})"
    )
    ui.notify("Methods paragraph copied to clipboard", type="positive")


async def _native_pick_files() -> list[str]:
    """Open macOS native file picker for multiple .ace files."""
    import asyncio
    loop = asyncio.get_event_loop()

    def _run_picker():
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'set theFiles to choose file of type {"ace"} with prompt "Select .ace files to compare" with multiple selections allowed',
                "-e",
                "set output to {}",
                "-e",
                "repeat with f in theFiles",
                "-e",
                "set end of output to POSIX path of f",
                "-e",
                "end repeat",
                "-e",
                'set AppleScript\'s text item delimiters to "\\n"',
                "-e",
                "return output as text",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result

    try:
        result = await loop.run_in_executor(None, _run_picker)
        if result.returncode != 0:
            return []
        paths = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
        return paths
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _export_per_code_csv(result):
    """Export per-code metrics as CSV download."""
    import csv
    import io
    from datetime import date

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "code_name", "n_positions", "percent_agreement",
        "cohens_kappa", "krippendorffs_alpha", "fleiss_kappa",
        "gwets_ac1", "brennan_prediger", "congers_kappa",
    ])
    for code_name, m in sorted(result.per_code.items()):
        writer.writerow([
            code_name, m.n_positions, f"{m.percent_agreement:.4f}",
            f"{m.cohens_kappa:.4f}" if m.cohens_kappa is not None else "",
            f"{m.krippendorffs_alpha:.4f}" if m.krippendorffs_alpha is not None else "",
            f"{m.fleiss_kappa:.4f}" if m.fleiss_kappa is not None else "",
            f"{m.gwets_ac1:.4f}" if m.gwets_ac1 is not None else "",
            f"{m.brennan_prediger:.4f}" if m.brennan_prediger is not None else "",
            f"{m.congers_kappa:.4f}" if m.congers_kappa is not None else "",
        ])

    ui.download(buf.getvalue().encode(), f"agreement_by_code_{date.today()}.csv")


def _export_per_source_csv(result):
    """Export per-source metrics as CSV download."""
    import csv
    import io
    from datetime import date

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "source_display_id", "n_positions", "percent_agreement",
        "krippendorffs_alpha", "kappa",
    ])
    for src_id, m in sorted(result.per_source.items()):
        kappa = m.cohens_kappa if m.cohens_kappa is not None else m.fleiss_kappa
        writer.writerow([
            src_id, m.n_positions, f"{m.percent_agreement:.4f}",
            f"{m.krippendorffs_alpha:.4f}" if m.krippendorffs_alpha is not None else "",
            f"{kappa:.4f}" if kappa is not None else "",
        ])

    ui.download(buf.getvalue().encode(), f"agreement_by_source_{date.today()}.csv")
