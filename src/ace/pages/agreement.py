"""Agreement dashboard page — /agreement route."""

import json
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
        file_list_container = ui.column().classes("items-center full-width gap-0")
        validation_container = ui.column().classes("items-center full-width q-mt-sm")
        results_container = ui.column().classes("items-center full-width")

        with ui.column().classes("mx-auto q-pa-lg items-center").style(
            "max-width: 800px; width: 100%;"
        ):
            ui.label("Inter-Coder Agreement").classes(
                "text-h5 text-weight-bold"
            ).style("letter-spacing: -0.01em;")

            # Empty state
            with ui.column().classes(
                "items-center full-width ace-empty-state q-mt-md"
            ) as empty_state:
                ui.label("Add .ace files to compare").classes(
                    "text-body1 text-grey-6"
                )
                ui.label(
                    "Two or more project files from different coders"
                ).classes("text-caption text-grey-5 q-mt-xs")

            file_list_container.move(target_index=-1)

            # Add File button
            ui.button(
                "Add File",
                icon="add",
                on_click=lambda: _pick_and_add_file(
                    loader, file_list_container, validation_container,
                    compute_btn, empty_state,
                ),
            ).props("flat dense no-caps").classes("text-grey-8 q-mt-sm")

            validation_container.move(target_index=-1)

            compute_btn = ui.button(
                "Compute Agreement",
                icon="calculate",
                on_click=lambda: _run_computation(loader, results_container),
            ).props("unelevated no-caps").classes("ace-compute-btn q-mt-md")
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
            ui.label(
                f"{info['filename']} \u2014 {info['source_count']} sources, "
                f"{info['annotation_count']} annotations"
            ).classes("ace-metadata").style("padding: 4px 0;")

    # Update validation
    if loader.file_count >= 2:
        empty_state.set_visibility(False)
        validation = loader.validate()
        validation_container.clear()
        with validation_container:
            for w in validation.get("warnings", []):
                ui.label(w).classes("ace-validation ace-validation--warn")

            if validation["valid"]:
                ui.label(
                    f"{validation['matched_sources']} sources, "
                    f"{validation['matched_codes']} codes matched \u2014 "
                    f"Coders: {', '.join(validation['coders'])}"
                ).classes("ace-validation ace-validation--ok")
                compute_btn.set_visibility(True)
            else:
                ui.label(validation["error"]).classes(
                    "ace-validation ace-validation--error"
                )
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
    """Render the full agreement dashboard — single scrolling page."""
    alpha_val = result.overall.krippendorffs_alpha
    alpha_str = f"{alpha_val:.3f}" if alpha_val is not None else "N/A"
    label, _ = _agreement_label(alpha_val)

    if result.n_coders == 2:
        kappa_label = "Cohen's Kappa"
        kappa_val = result.overall.cohens_kappa
    else:
        kappa_label = "Fleiss' Kappa"
        kappa_val = result.overall.fleiss_kappa
    kappa_str = f"{kappa_val:.3f}" if kappa_val is not None else "N/A"
    pct_str = f"{result.overall.percent_agreement:.1%}"

    # ── Headline metrics + pairwise side by side ──────────────
    ui.separator().classes("q-my-md")

    with ui.row().classes("full-width gap-6").style("flex-wrap: wrap;"):
        # Left: metrics
        with ui.column().classes("gap-1").style("flex: 1; min-width: 300px;"):
            _render_metric_line("Krippendorff's Alpha", alpha_str, label)
            _render_metric_line(kappa_label, kappa_str)
            _render_metric_line("Percent Agreement", pct_str)

            ui.label(
                f"{result.n_sources} sources \u00b7 {result.n_codes} codes \u00b7 "
                f"{result.n_coders} coders"
            ).classes("ace-metadata q-mt-sm")

        # Right: pairwise heatmap (3+ coders only)
        if result.n_coders > 2:
            with ui.column().classes("gap-1").style("flex: 1; min-width: 280px;"):
                _render_pairwise(result, dataset)

    # ── Agreement by Code ─────────────────────────────────────
    ui.separator().classes("q-my-md")
    _render_per_code_table(result)

    # ── Methods paragraph ─────────────────────────────────────
    ui.separator().classes("q-my-md")
    _render_methods_paragraph(result)


def _render_metric_line(label: str, value: str, qualifier: str = ""):
    """Render a single metric as a line: Label  Value  Qualifier."""
    with ui.row().classes("items-center gap-3"):
        ui.label(label).classes("text-body2 text-grey-7").style(
            "width: 170px; text-align: right;"
        )
        ui.label(value).classes("ace-metric-lg")
        if qualifier:
            ui.label(qualifier).classes("text-caption text-grey-6")


def _render_per_code_table(result):
    """Render the per-code agreement table with all metrics.

    Primary metrics (% Agreement, K. Alpha, Kappa) are visually prominent.
    Secondary metrics (AC1, B-P, Conger, Fleiss) are shown in lighter text.
    """
    # Primary columns get class "ace-col-primary", secondary get "ace-col-secondary"
    columns = [
        {"name": "code", "label": "Code Name", "field": "code", "sortable": True, "align": "left",
         "classes": "ace-col-primary", "headerClasses": "ace-col-primary"},
        {"name": "pct", "label": "% Agree", "field": "pct", "sortable": True,
         "classes": "ace-col-primary", "headerClasses": "ace-col-primary"},
        {"name": "alpha", "label": "K. Alpha", "field": "alpha", "sortable": True,
         "classes": "ace-col-primary", "headerClasses": "ace-col-primary"},
        {"name": "kappa", "label": "Kappa", "field": "kappa", "sortable": True,
         "classes": "ace-col-primary", "headerClasses": "ace-col-primary"},
        {"name": "ac1", "label": "AC1", "field": "ac1", "sortable": True,
         "classes": "ace-col-secondary", "headerClasses": "ace-col-secondary"},
        {"name": "bp", "label": "B-P", "field": "bp", "sortable": True,
         "classes": "ace-col-secondary", "headerClasses": "ace-col-secondary"},
        {"name": "conger", "label": "Conger", "field": "conger", "sortable": True,
         "classes": "ace-col-secondary", "headerClasses": "ace-col-secondary"},
        {"name": "fleiss", "label": "Fleiss", "field": "fleiss", "sortable": True,
         "classes": "ace-col-secondary", "headerClasses": "ace-col-secondary"},
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
        })

    with ui.row().classes("items-center justify-between full-width q-mb-sm"):
        ui.label("Agreement by Code").classes("ace-section-header")
        ui.button(
            "Export CSV",
            icon="download",
            on_click=lambda: _export_per_code_csv(result),
        ).props("flat dense no-caps").classes("text-grey-8")

    ui.table(
        columns=columns, rows=rows, row_key="code",
    ).props("flat dense").classes("full-width ace-data-table")


def _render_pairwise(result, dataset):
    """Render the pairwise heatmap."""
    ui.label("Pairwise").classes("ace-section-header")

    coders = dataset.coders
    n = len(coders)

    matrix = [[None] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0
        for j in range(i + 1, n):
            key = (coders[i].id, coders[j].id)
            alt_key = (coders[j].id, coders[i].id)
            val = result.pairwise.get(key) or result.pairwise.get(alt_key)
            matrix[i][j] = val
            matrix[j][i] = val

    html = '<table class="ace-heatmap"><tr><th></th>'
    for c in coders:
        html += f"<th>{c.label}</th>"
    html += "</tr>"

    for i, coder in enumerate(coders):
        html += f"<tr><th>{coder.label}</th>"
        for j in range(n):
            val = matrix[i][j]
            if val is None:
                html += "<td>\u2014</td>"
            elif i == j:
                html += '<td class="ace-heatmap-diag">\u2014</td>'
            else:
                bg = _heatmap_color(val)
                text_color = "#ffffff" if val > 0.6 else "#212121"
                html += (
                    f'<td style="background-color: {bg}; color: {text_color};">'
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


def _render_methods_paragraph(result):
    """Render the methods paragraph inline with a copy button."""
    para = _build_methods_text(result)

    with ui.row().classes("items-start full-width q-mb-sm"):
        ui.label("Methods Paragraph").classes("ace-section-header").style(
            "border-bottom: none; margin-bottom: 0; padding-bottom: 0; flex: 1;"
        )
        ui.button(
            icon="content_copy",
            on_click=lambda: _copy_to_clipboard(para),
        ).props("flat dense round").classes("text-grey-7")

    ui.label(para).classes("text-body2 text-grey-8").style(
        "line-height: 1.6; font-style: italic;"
    )


def _build_methods_text(result) -> str:
    """Generate a publication-ready methods paragraph."""
    alpha = result.overall.krippendorffs_alpha
    alpha_str = f"{alpha:.2f}" if alpha is not None else "N/A"

    if result.n_coders == 2:
        kappa = result.overall.cohens_kappa
        kappa_label = "Cohen's kappa"
    else:
        kappa = result.overall.fleiss_kappa
        kappa_label = "Fleiss' kappa"
    kappa_str = f"{kappa:.2f}" if kappa is not None else "N/A"

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

    return (
        f"Inter-coder reliability was assessed using Krippendorff's alpha "
        f"(\u03B1 = {alpha_str}) and {kappa_label} "
        f"(\u03BA = {kappa_str}) across {result.n_coders} coders "
        f"and {result.n_sources} source texts.{range_str}"
    )


async def _copy_to_clipboard(text: str):
    """Copy text to clipboard via browser API."""
    await ui.run_javascript(
        f"navigator.clipboard.writeText({json.dumps(text)})"
    )
    ui.notify("Copied to clipboard", type="positive")


def _agreement_label(value: float | None) -> tuple[str, str]:
    """Return (verbal label, css-level) for the Landis & Koch scale."""
    if value is None:
        return ("", "")
    if value < 0.0:
        return ("Poor", "poor")
    if value <= 0.20:
        return ("Slight", "slight")
    if value <= 0.40:
        return ("Fair", "fair")
    if value <= 0.60:
        return ("Moderate", "moderate")
    if value <= 0.80:
        return ("Substantial", "substantial")
    return ("Almost Perfect", "almost-perfect")


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
