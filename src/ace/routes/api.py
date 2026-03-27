"""API routes — JSON/HTMX fragment responses."""

from __future__ import annotations

import asyncio
import html
import platform
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, Response

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _accept_to_types(accept: str | None) -> str:
    """Convert an accept filter like ".ace,.csv" to osascript type list."""
    if not accept:
        return ""
    extensions = [ext.lstrip(".").strip() for ext in accept.split(",") if ext.strip()]
    if not extensions:
        return ""
    quoted = ", ".join(f'"{e}"' for e in extensions)
    return f" of type {{{quoted}}}"


def _run_osascript(script: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Native file picker endpoints
# ---------------------------------------------------------------------------

@router.post("/native/pick-file")
async def pick_file(accept: str | None = Form(default=None)):
    """Open a native macOS file picker and return the selected path."""
    if platform.system() != "Darwin":
        return JSONResponse({"path": ""})

    type_filter = _accept_to_types(accept)
    script = f'POSIX path of (choose file{type_filter})'
    result = await asyncio.to_thread(_run_osascript, script)

    path = result.stdout.strip() if result.returncode == 0 else ""
    return JSONResponse({"path": path})


@router.post("/native/pick-folder")
async def pick_folder():
    """Open a native macOS folder picker and return the selected path."""
    if platform.system() != "Darwin":
        return JSONResponse({"path": ""})

    script = 'POSIX path of (choose folder)'
    result = await asyncio.to_thread(_run_osascript, script)

    path = result.stdout.strip() if result.returncode == 0 else ""
    return JSONResponse({"path": path})


@router.post("/native/pick-files")
async def pick_files(accept: str | None = Form(default=None)):
    """Open a native macOS file picker (multiple selection) and return paths."""
    if platform.system() != "Darwin":
        return JSONResponse({"paths": []})

    type_filter = _accept_to_types(accept)
    script = (
        f'set theFiles to (choose file{type_filter}'
        f' with multiple selections allowed)\n'
        f'set output to ""\n'
        f'repeat with f in theFiles\n'
        f'  set output to output & POSIX path of f & linefeed\n'
        f'end repeat\n'
        f'return output'
    )
    result = await asyncio.to_thread(_run_osascript, script)

    if result.returncode == 0:
        paths = [p for p in result.stdout.strip().split("\n") if p]
    else:
        paths = []
    return JSONResponse({"paths": paths})


# ---------------------------------------------------------------------------
# OOB toast helper
# ---------------------------------------------------------------------------

def _oob_toast(message: str, variant: str = "error") -> HTMLResponse:
    """Return an OOB-swap toast element for HTMX."""
    return HTMLResponse(
        f'<div id="toast" hx-swap-oob="beforeend">'
        f'<div class="toast-msg ace-toast--{variant}">{message}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Project create / open
# ---------------------------------------------------------------------------

@router.post("/project/create")
async def project_create(
    request: Request,
    name: str = Form(...),
    path: str = Form(...),
    overwrite: bool = Form(default=False),
):
    """Create a new .ace project file."""
    from ace.db.connection import create_project
    from ace.models.coder import list_coders

    file_path = Path(path)

    # Ensure the path ends with .ace
    if file_path.suffix != ".ace":
        file_path = file_path.with_suffix(".ace")

    try:
        if file_path.exists() and not overwrite:
            # Return an overwrite confirmation dialog
            return HTMLResponse(
                '<dialog open class="ace-dialog">'
                "<p>This file already exists. Overwrite it?</p>"
                '<form method="dialog" style="display:flex;gap:0.5rem;margin-top:1rem;justify-content:flex-end">'
                '<button class="ace-btn" onclick="this.closest(\'dialog\').remove()" type="button">Cancel</button>'
                f'<button class="ace-btn ace-btn--danger" '
                f'hx-post="/api/project/create" '
                f'hx-vals=\'{{"name":"{name}","path":"{file_path}","overwrite":"true"}}\' '
                f'hx-target="#modal-container" '
                f'hx-swap="innerHTML"'
                f">Overwrite</button>"
                "</form>"
                "</dialog>"
            )

        if file_path.exists() and overwrite:
            file_path.unlink()

        conn = create_project(str(file_path), name)
        coders = list_coders(conn)
        coder_id = coders[0]["id"] if coders else None
        conn.close()

        request.app.state.project_path = str(file_path)
        if coder_id:
            request.app.state.coder_id = coder_id
        request.app.state.active_projects.add(str(file_path))

        return Response(
            status_code=200,
            headers={"HX-Redirect": "/import"},
        )
    except Exception as e:
        return _oob_toast(f"Failed to create project: {e}")


@router.post("/project/open")
async def project_open(request: Request, path: str = Form(...)):
    """Open an existing .ace project file."""
    from ace.db.connection import open_project
    from ace.models.coder import list_coders
    from ace.models.source import list_sources

    try:
        conn = open_project(path)
    except (ValueError, FileNotFoundError, sqlite3.DatabaseError) as e:
        return _oob_toast(str(e))

    try:
        coders = list_coders(conn)
        coder_id = coders[0]["id"] if coders else None
        sources = list_sources(conn)
    finally:
        conn.close()

    request.app.state.project_path = str(path)
    if coder_id:
        request.app.state.coder_id = coder_id
    request.app.state.active_projects.add(str(path))

    redirect = "/code" if sources else "/import"
    return Response(
        status_code=200,
        headers={"HX-Redirect": redirect},
    )


# ---------------------------------------------------------------------------
# Import routes
# ---------------------------------------------------------------------------

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/import/upload")
async def import_upload(request: Request, file: UploadFile = File(...)):
    """Accept a CSV/Excel upload, parse it, return a preview table fragment."""
    from ace.services.importer import _read_tabular

    # Read the uploaded file into a temp file
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        return _oob_toast("File exceeds 50 MB limit")

    suffix = Path(file.filename or "upload.csv").suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.close()

        rows, columns = _read_tabular(Path(tmp.name))
    except Exception as e:
        Path(tmp.name).unlink(missing_ok=True)
        return _oob_toast(f"Could not parse file: {e}")

    # Store temp path for the commit step
    request.app.state.import_tmp_path = tmp.name

    # Build preview HTML
    preview_rows = rows[:10]

    # Table header
    th = "".join(f"<th>{html.escape(str(c))}</th>" for c in columns)

    # Table body
    tbody = ""
    for row in preview_rows:
        cells = "".join(
            f"<td>{html.escape(str(row.get(c, '')))}</td>" for c in columns
        )
        tbody += f"<tr>{cells}</tr>"

    row_note = ""
    if len(rows) > 10:
        row_note = f'<p style="color:var(--ace-text-muted);font-size:0.8rem;margin-top:0.5rem">Showing 10 of {len(rows)} rows</p>'

    # Column selection: ID dropdown + text column checkboxes
    id_options = "".join(
        f'<option value="{html.escape(str(c))}">{html.escape(str(c))}</option>'
        for c in columns
    )

    text_checks = "".join(
        f'<label style="display:block;margin-bottom:0.25rem">'
        f'<input type="checkbox" name="text_columns" value="{html.escape(str(c))}"> '
        f'{html.escape(str(c))}'
        f'</label>'
        for c in columns
    )

    fragment = f"""
    <div class="ace-table-wrap" style="overflow-x:auto;margin-bottom:1rem">
      <table class="ace-table">
        <thead><tr>{th}</tr></thead>
        <tbody>{tbody}</tbody>
      </table>
      {row_note}
    </div>

    <form hx-post="/api/import/commit" hx-target="#import-preview" hx-swap="innerHTML">
      <div style="display:flex;gap:2rem;margin-bottom:1rem">
        <div>
          <label class="ace-label">ID column</label>
          <select name="id_column" class="ace-input" style="width:auto">
            {id_options}
          </select>
        </div>
        <div>
          <label class="ace-label">Text column(s)</label>
          {text_checks}
        </div>
      </div>
      <button type="submit" class="ace-btn ace-btn--primary">Import</button>
    </form>
    """
    return HTMLResponse(fragment)


@router.post("/import/commit")
async def import_commit(
    request: Request,
    id_column: str = Form(...),
    text_columns: list[str] = Form(...),
):
    """Commit the uploaded file: import selected columns as sources."""
    from ace.app import get_db
    from ace.services.importer import import_csv

    tmp_path = getattr(request.app.state, "import_tmp_path", None)
    if tmp_path is None or not Path(tmp_path).exists():
        return _oob_toast("No uploaded file found. Please upload again.")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        count = import_csv(conn, tmp_path, id_column, text_columns)
    except Exception as e:
        db_gen.close()
        return _oob_toast(f"Import failed: {e}")
    finally:
        db_gen.close()

    # Clean up temp file
    Path(tmp_path).unlink(missing_ok=True)
    request.app.state.import_tmp_path = None

    return HTMLResponse(
        f'<div style="padding:1rem;border:1px solid var(--ace-success);color:var(--ace-success)">'
        f'<p>Imported {count} source{"s" if count != 1 else ""} successfully.</p>'
        f'<a href="/code" class="ace-btn ace-btn--primary" style="margin-top:0.5rem;display:inline-block;text-decoration:none">Start coding &rarr;</a>'
        f'</div>'
    )


@router.post("/import/folder")
async def import_folder(
    request: Request,
    path: str = Form(...),
):
    """Import .txt files from a folder."""
    from ace.app import get_db
    from ace.services.importer import import_text_files

    folder = Path(path)
    if not folder.is_dir():
        return _oob_toast("Invalid folder path.")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        count = import_text_files(conn, folder)
    except Exception as e:
        db_gen.close()
        return _oob_toast(f"Import failed: {e}")
    finally:
        db_gen.close()

    return HTMLResponse(
        f'<div style="padding:1rem;border:1px solid var(--ace-success);color:var(--ace-success)">'
        f'<p>Imported {count} text file{"s" if count != 1 else ""} successfully.</p>'
        f'<a href="/code" class="ace-btn ace-btn--primary" style="margin-top:0.5rem;display:inline-block;text-decoration:none">Start coding &rarr;</a>'
        f'</div>'
    )
