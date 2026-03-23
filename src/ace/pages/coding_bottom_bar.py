"""Bottom bar and source grid navigator for the coding page."""

import html

from nicegui import ui

from ace.models.annotation import get_annotation_counts_by_source


def build_bottom_bar(*, conn, coder_id, assignments, state, sources, navigate_to_fn):
    """Build the grid navigator and bottom navigation bar.

    Returns (grid_container, bottom_bar, toggle_grid) so that callers
    can wire up shortcuts and refresh callbacks.
    """
    sources_by_id = {s["id"]: s for s in sources}

    # ── Source Grid Navigator ────────────────────────────────────────

    grid_container = ui.column().classes("full-width").style(
        "border-top: 1px solid #bdbdbd; background: #f5f5f5;"
    )
    grid_container.set_visibility(False)

    def _build_grid_html():
        counts = get_annotation_counts_by_source(conn, coder_id)
        max_count = max(counts.values()) if counts else 1
        total = len(assignments)
        cell_size = max(10, min(24, int((700 * 200 / max(total, 1)) ** 0.5)))
        cells = []
        for i, asn in enumerate(assignments):
            sid = asn["source_id"]
            count = counts.get(sid, 0)
            is_current = i == state["current_index"]
            is_flagged = asn["status"] == "flagged"
            if is_current:
                bg = "#222"
            else:
                lightness = 95 - int(65 * count / max_count) if max_count else 95
                bg = f"hsl(210, 70%, {lightness}%)"
            border = "2px solid #d84315" if is_flagged else ("2px solid white" if is_current else "1px solid #bdbdbd")
            src = sources_by_id.get(sid)
            display_id = src["display_id"] if src else f"Source {i + 1}"
            safe_title = html.escape(f"{display_id} ({count} annotations)", quote=True)
            cells.append(
                f'<span class="ace-grid-cell" data-idx="{i}" '
                f'title="{safe_title}" '
                f'style="width:{cell_size}px;height:{cell_size}px;background:{bg};'
                f'border:{border};display:inline-block;"></span>'
            )
        legend = (
            '<div class="ace-grid-legend">'
            f'<span><span style="display:inline-block;width:10px;height:10px;background:hsl(210,70%,95%);border:1px solid #ccc;"></span> 0</span>'
            f'<span><span style="display:inline-block;width:10px;height:10px;background:hsl(210,70%,60%);border:1px solid #ccc;"></span> some</span>'
            f'<span><span style="display:inline-block;width:10px;height:10px;background:hsl(210,70%,30%);border:1px solid #ccc;"></span> most</span>'
            f'<span><span style="display:inline-block;width:10px;height:10px;background:#222;border:2px solid white;"></span> current</span>'
            f'<span><span style="display:inline-block;width:10px;height:10px;background:hsl(210,70%,80%);border:2px solid #d84315;"></span> flagged</span>'
            '</div>'
        )
        return legend + '<div class="ace-source-grid">' + "".join(cells) + "</div>"

    grid_html = ui.html("", sanitize=False)
    grid_html.move(grid_container)

    def _toggle_grid():
        visible = grid_container.visible
        if not visible:
            grid_html.content = _build_grid_html()
        grid_container.set_visibility(not visible)

    def _on_grid_cell_clicked(e):
        idx = e.args.get("index")
        if idx is not None and 0 <= idx < len(assignments):
            grid_container.set_visibility(False)
            navigate_to_fn(idx)

    ui.on("grid_cell_clicked", _on_grid_cell_clicked)

    # ── Bottom Bar ────────────────────────────────────────────────────
    @ui.refreshable
    def bottom_bar():
        total = len(assignments)
        complete_count = sum(1 for a in assignments if a["status"] == "complete")
        pct = round(complete_count / total * 100) if total else 0
        idx = state["current_index"]

        with ui.row().classes(
            "items-center full-width q-pa-sm justify-between"
        ).style(
            "border-top: 1px solid #bdbdbd; background: #f5f5f5;"
        ):
            # Nav buttons
            with ui.row().classes("items-center gap-2"):
                ui.button(
                    "Prev",
                    icon="chevron_left",
                    on_click=lambda: navigate_to_fn(max(0, idx - 1)),
                ).props("flat dense" + (" disable" if idx == 0 else "")).tooltip("Alt+\u2190")

                ui.button(
                    f"Source {idx + 1} of {total} ({pct}% complete) \u25BE",
                    on_click=_toggle_grid,
                ).props("flat dense no-caps").classes("text-body2 text-grey-8").tooltip("G")

                ui.button(
                    "Next",
                    icon="chevron_right",
                    on_click=lambda: navigate_to_fn(min(total - 1, idx + 1)),
                ).props("flat dense" + (" disable" if idx >= total - 1 else "")).tooltip("Alt+\u2192")

    bottom_bar()

    return grid_container, bottom_bar, _toggle_grid
