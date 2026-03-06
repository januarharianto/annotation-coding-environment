"""Import step component for the manager wizard."""

import shutil
import tempfile
from pathlib import Path

import pandas as pd
from nicegui import events, ui

from ace.models.source import list_sources
from ace.services.importer import import_csv, import_text_files


def build(conn, stepper) -> None:
    """Build the Import step UI inside the current stepper step context.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection for the current project.
    stepper : ui.stepper
        The parent stepper widget, used to advance to the next step.
    """
    state = {
        "df": None,
        "file_path": None,
        "file_name": None,
        "folder_path": None,
        "import_mode": None,  # "tabular" or "text_files"
    }

    # -- Existing sources summary --
    existing = list_sources(conn)
    if existing:
        with ui.card().classes("full-width q-mb-md bg-blue-1"):
            ui.label(f"This project already has {len(existing)} imported source(s).").classes(
                "text-body2"
            )

    # -- Upload area --
    ui.label("Upload a CSV or Excel file to import data.").classes("text-body1 q-mb-sm")

    ui.upload(
        label="Drop CSV/Excel file here (or click to browse)",
        auto_upload=True,
        on_upload=lambda e: _handle_file_upload(e, state, preview_container, column_container, import_container),
    ).props('accept=".csv,.xlsx,.xls" flat bordered').classes("full-width")

    ui.label("or").classes("text-body2 text-grey-6 q-my-xs self-center")

    with ui.row().classes("items-center gap-2"):
        folder_input = ui.input(
            "Path to folder of .txt files",
            placeholder="/path/to/folder",
        ).classes("col-grow")
        ui.button(
            "Load folder",
            on_click=lambda: _handle_folder_load(
                folder_input.value, state, preview_container, column_container, import_container
            ),
        ).props("outline")

    # -- Preview container (hidden until file loaded) --
    preview_container = ui.column().classes("full-width q-mt-md")
    preview_container.set_visibility(False)

    # -- Column selection container --
    column_container = ui.column().classes("full-width q-mt-sm")
    column_container.set_visibility(False)

    # -- Import button / results container --
    import_container = ui.column().classes("full-width q-mt-sm")
    import_container.set_visibility(False)

    # Build column selection and import button (populated after file load)
    _build_column_ui(state, conn, stepper, column_container, import_container, preview_container)


def _handle_file_upload(e: events.UploadEventArguments, state, preview_container, column_container, import_container):
    """Handle uploaded CSV/Excel file."""
    name = e.name
    suffix = Path(name).suffix.lower()
    if suffix not in (".csv", ".xlsx", ".xls"):
        ui.notify("Please upload a CSV or Excel file.", type="warning")
        return

    # Save to temp file
    tmp_dir = Path(tempfile.mkdtemp())
    dest = tmp_dir / name
    with open(dest, "wb") as f:
        shutil.copyfileobj(e.content, f)

    # Read with pandas
    try:
        if suffix in (".xlsx", ".xls"):
            df = pd.read_excel(dest)
        else:
            df = pd.read_csv(dest)
    except Exception as exc:
        ui.notify(f"Error reading file: {exc}", type="negative")
        return

    state["df"] = df
    state["file_path"] = dest
    state["file_name"] = name
    state["folder_path"] = None
    state["import_mode"] = "tabular"

    _show_preview(df, name, preview_container)
    _show_column_selection(df, column_container)
    import_container.set_visibility(True)


def _handle_folder_load(folder_str, state, preview_container, column_container, import_container):
    """Handle loading a folder of .txt files."""
    folder_str = (folder_str or "").strip()
    if not folder_str:
        ui.notify("Please enter a folder path.", type="warning")
        return

    folder = Path(folder_str).expanduser().resolve()
    if not folder.is_dir():
        ui.notify("Folder not found.", type="negative")
        return

    txt_files = sorted(folder.glob("*.txt"))
    if not txt_files:
        ui.notify("No .txt files found in the folder.", type="warning")
        return

    state["df"] = None
    state["file_path"] = None
    state["file_name"] = None
    state["folder_path"] = folder
    state["import_mode"] = "text_files"

    # Show preview of text files
    preview_container.clear()
    with preview_container:
        ui.label(f"Found {len(txt_files)} .txt files in: {folder.name}/").classes(
            "text-subtitle2 text-weight-medium"
        )
        rows = []
        for tf in txt_files[:10]:
            content = tf.read_text(encoding="utf-8")
            preview_text = content[:100] + ("..." if len(content) > 100 else "")
            rows.append({"filename": tf.name, "preview": preview_text})

        columns = [
            {"name": "filename", "label": "Filename", "field": "filename", "align": "left"},
            {"name": "preview", "label": "Content Preview", "field": "preview", "align": "left"},
        ]
        ui.table(columns=columns, rows=rows).classes("full-width")
        if len(txt_files) > 10:
            ui.label(f"... and {len(txt_files) - 10} more files").classes("text-caption text-grey-6")

    preview_container.set_visibility(True)

    # Hide column selection for text files
    column_container.set_visibility(False)

    # Show import button
    import_container.set_visibility(True)


def _show_preview(df: pd.DataFrame, name: str, preview_container):
    """Show a preview table of the uploaded data."""
    preview_container.clear()
    with preview_container:
        ui.label(f"Preview of {name} ({len(df)} rows, {len(df.columns)} columns)").classes(
            "text-subtitle2 text-weight-medium"
        )

        preview_df = df.head(10)
        columns = [
            {"name": col, "label": col, "field": col, "align": "left", "sortable": True}
            for col in preview_df.columns
        ]
        rows = []
        for _, row in preview_df.iterrows():
            row_dict = {}
            for col in preview_df.columns:
                val = row[col]
                if pd.isna(val):
                    row_dict[col] = ""
                else:
                    s = str(val)
                    row_dict[col] = s[:80] + ("..." if len(s) > 80 else "")
            rows.append(row_dict)

        ui.table(columns=columns, rows=rows).classes("full-width")

    preview_container.set_visibility(True)


def _show_column_selection(df: pd.DataFrame, column_container):
    """Show column selection dropdowns for ID and text columns."""
    column_container.clear()
    cols = list(df.columns)

    with column_container:
        ui.label("Select columns").classes("text-subtitle2 text-weight-medium q-mt-sm")

        with ui.row().classes("items-start gap-4 full-width"):
            with ui.column().classes("col"):
                ui.label("ID column (participant identifier)").classes("text-caption")
                id_select = ui.select(
                    options=cols, value=cols[0], label="ID column"
                ).classes("full-width").props("outlined")
                id_select._props["name"] = "id_column"

            with ui.column().classes("col"):
                ui.label("Text column(s) to code").classes("text-caption")
                text_select = ui.select(
                    options=cols, value=[cols[1]] if len(cols) > 1 else [cols[0]],
                    label="Text columns", multiple=True,
                ).classes("full-width").props("outlined use-chips")
                text_select._props["name"] = "text_columns"

    column_container.set_visibility(True)


def _build_column_ui(state, conn, stepper, column_container, import_container, preview_container):
    """Build the import button and results area inside import_container."""
    with import_container:
        ui.separator().classes("q-my-sm")

        async def _do_import():
            mode = state.get("import_mode")
            if not mode:
                ui.notify("No file loaded.", type="warning")
                return

            if mode == "text_files":
                folder = state.get("folder_path")
                if not folder:
                    ui.notify("No folder loaded.", type="warning")
                    return
                try:
                    count = import_text_files(conn, folder)
                    ui.notify(f"Imported {count} sources from text files.", type="positive")
                    _show_result(count, folder.name, result_card)
                except Exception as exc:
                    ui.notify(f"Import failed: {exc}", type="negative")
                    return

            elif mode == "tabular":
                df = state.get("df")
                file_path = state.get("file_path")
                file_name = state.get("file_name")
                if df is None or file_path is None:
                    ui.notify("No file loaded.", type="warning")
                    return

                # Read column selections from column_container children
                id_col = _find_select_value(column_container, "id_column")
                text_cols = _find_select_value(column_container, "text_columns")

                if not id_col:
                    ui.notify("Please select an ID column.", type="warning")
                    return
                if not text_cols:
                    ui.notify("Please select at least one text column.", type="warning")
                    return

                if isinstance(text_cols, str):
                    text_cols = [text_cols]

                try:
                    count = import_csv(conn, file_path, id_col, text_cols)
                    ui.notify(f"Imported {count} sources from {file_name}.", type="positive")
                    _show_result(count, file_name, result_card)
                except Exception as exc:
                    ui.notify(f"Import failed: {exc}", type="negative")
                    return

        ui.button("Import", icon="upload", on_click=_do_import).props("unelevated color=primary")

        result_card = ui.card().classes("full-width q-mt-md bg-green-1")
        result_card.set_visibility(False)

        with ui.row().classes("q-mt-md justify-end"):
            ui.button(
                "Next: Codebook", icon="arrow_forward",
                on_click=lambda: stepper.next(),
            ).props("unelevated")


def _show_result(count: int, name: str, result_card):
    """Show the import result summary."""
    result_card.clear()
    with result_card:
        ui.icon("check_circle", color="green").classes("text-h5")
        ui.label(f"Successfully imported {count} source(s) from {name}.").classes(
            "text-body1 text-weight-medium"
        )
    result_card.set_visibility(True)


def _find_select_value(container, name: str):
    """Search descendants of a NiceGUI container for a ui.select with the given name prop."""
    for child in container.descendants():
        props = getattr(child, "_props", {})
        if props.get("name") == name:
            return child.value
    return None
