"""Import sources from CSV/Excel files and text file folders."""

import sqlite3
from pathlib import Path

import pandas as pd

from ace.models.source import add_source


def import_csv(
    conn: sqlite3.Connection,
    path: str | Path,
    id_column: str,
    text_columns: list[str],
) -> int:
    """Import rows from a CSV or Excel file as sources.

    Each row x text_column combination becomes one source.
    Non-ID/non-text columns are stored as metadata_json.
    Returns the number of sources created.
    """
    path = Path(path)
    df = _read_tabular(path)

    meta_columns = [c for c in df.columns if c != id_column and c not in text_columns]
    multi = len(text_columns) > 1
    count = 0

    for _, row in df.iterrows():
        display_base = str(row[id_column])
        metadata = {c: _to_native(row[c]) for c in meta_columns} if meta_columns else None

        for col in text_columns:
            if multi:
                display_id = f"{display_base}_{col}"
            else:
                display_id = display_base

            add_source(
                conn,
                display_id=display_id,
                content_text=str(row[col]),
                source_type="row",
                filename=path.name,
                source_column=col if multi else None,
                metadata=metadata,
            )
            count += 1

    return count


def import_text_files(
    conn: sqlite3.Connection,
    folder: str | Path,
) -> int:
    """Import all .txt files from a folder as sources.

    Each file becomes one source with display_id = filename stem.
    Returns the number of sources created.
    """
    folder = Path(folder)
    count = 0

    for txt_path in sorted(folder.glob("*.txt")):
        content = txt_path.read_text(encoding="utf-8")
        add_source(
            conn,
            display_id=txt_path.stem,
            content_text=content,
            source_type="file",
            filename=txt_path.name,
        )
        count += 1

    return count


def _read_tabular(path: Path) -> pd.DataFrame:
    """Read a CSV or Excel file into a DataFrame, trying multiple encodings for CSV."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)

    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "multi", b"", 0, 1, f"Could not decode {path} with utf-8, latin-1, or cp1252"
    )


def _to_native(value):
    """Convert pandas/numpy scalar to native Python type for JSON serialization."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value
