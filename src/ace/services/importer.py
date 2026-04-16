"""Import sources from CSV/Excel files and text file folders."""

import csv
import random
import sqlite3
from datetime import datetime
from pathlib import Path

import openpyxl

from ace.models.source import add_source

_CSV_ENCODINGS = ("utf-8", "latin-1", "cp1252")
_TEXT_EXTENSIONS = ("*.txt", "*.md")


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
    rows, columns = read_tabular(path)

    meta_columns = [c for c in columns if c != id_column and c not in text_columns]
    multi = len(text_columns) > 1
    count = 0

    for row in rows:
        display_base = str(row[id_column])
        metadata = {c: row[c] for c in meta_columns} if meta_columns else None

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


def _list_text_files(folder: Path) -> list[Path]:
    """Return regular text files (.txt, .md) in folder, sorted by name."""
    files = []
    for pattern in _TEXT_EXTENSIONS:
        files.extend(p for p in folder.glob(pattern) if p.is_file())
    files.sort(key=lambda p: p.name)
    return files


def import_text_files(
    conn: sqlite3.Connection,
    folder: str | Path,
) -> int:
    """Import text files (.txt, .md) from a folder as sources.

    Each file becomes one source with display_id = filename stem.
    Returns the number of sources created.
    """
    count = 0
    for txt_path in _list_text_files(Path(folder)):
        content = _read_text_file(txt_path)
        add_source(
            conn,
            display_id=txt_path.stem,
            content_text=content,
            source_type="file",
            filename=txt_path.name,
        )
        count += 1

    return count


def get_random_preview(
    folder: str | Path,
    max_chars: int = 500,
) -> tuple[str, str] | None:
    """Pick a random text file from folder and return (filename, snippet).

    Returns None if no text files exist.
    """
    files = _list_text_files(Path(folder))
    if not files:
        return None

    chosen = random.choice(files)
    content = _read_text_file(chosen)
    if len(content) > max_chars:
        content = content[:max_chars] + "..."
    return chosen.name, content


def read_tabular(path: Path) -> tuple[list[dict], list[str]]:
    """Read a CSV or Excel file, returning (rows as dicts, column names)."""
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return _read_xlsx(path)
    return _read_csv(path)


def _read_csv(path: Path) -> tuple[list[dict], list[str]]:
    """Read CSV with multi-encoding fallback (utf-8, latin-1, cp1252)."""
    for encoding in _CSV_ENCODINGS:
        try:
            with open(path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                columns = reader.fieldnames or []
                rows = []
                for row in reader:
                    coerced = {k: _coerce_value(v) for k, v in row.items()}
                    rows.append(coerced)
                return rows, list(columns)
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "multi", b"", 0, 1, f"Could not decode {path} with utf-8, latin-1, or cp1252"
    )


def _read_xlsx(path: Path) -> tuple[list[dict], list[str]]:
    """Read first sheet of .xlsx with openpyxl (read-only, data-only)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        row_iter = ws.iter_rows()
        header_cells = next(row_iter)
        columns = [str(c.value) if c.value is not None else f"col_{i}" for i, c in enumerate(header_cells)]

        rows = []
        for row_cells in row_iter:
            row = {}
            for col_name, cell in zip(columns, row_cells):
                value = cell.value
                if isinstance(value, datetime):
                    value = value.isoformat()
                row[col_name] = value
            rows.append(row)
        return rows, columns
    finally:
        wb.close()


def _read_text_file(path: Path) -> str:
    """Read a text file with multi-encoding fallback."""
    for encoding in _CSV_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "multi", b"", 0, 1, f"Could not decode {path} with utf-8, latin-1, or cp1252"
    )


def _coerce_value(value: str):
    """Coerce a CSV string value to int, float, or leave as string.

    Empty strings become None.
    """
    if value == "":
        return None
    try:
        int_val = int(value)
        # Avoid converting "07" to 7 — preserve as string if leading zero
        if value != str(int_val):
            return value
        return int_val
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value
