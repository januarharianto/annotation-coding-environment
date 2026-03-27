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

    # Build glimpse-style preview
    filename = html.escape(file.filename or "upload")
    n_rows = len(rows)
    n_cols = len(columns)
    sample_rows = rows[:8]

    def _infer_type(col_name: str) -> str:
        """Infer column type from first non-None values."""
        for row in sample_rows:
            v = row.get(col_name)
            if v is None or v == "":
                continue
            if isinstance(v, (int, float)):
                return "num"
            s = str(v)
            try:
                float(s)
                return "num"
            except (ValueError, TypeError):
                pass
            return "chr"
        return "chr"

    def _sample_values(col_name: str) -> str:
        """Get comma-joined sample values, truncated."""
        vals = []
        for row in sample_rows:
            v = row.get(col_name)
            if v is None:
                vals.append("NA")
            else:
                s = str(v)
                if len(s) > 30:
                    s = s[:28] + "\u2026"
                vals.append(s)
        return html.escape(", ".join(vals)) + " \u2026"

    # Glimpse rows with inline role toggles
    glimpse_rows = ""
    for col in columns:
        col_type = _infer_type(col)
        sample = _sample_values(col)
        esc_col = html.escape(str(col))
        glimpse_rows += (
            f'<div class="ace-glimpse-row" data-col="{esc_col}" data-role="" tabindex="0">'
            f'<span class="ace-glimpse-name">{esc_col}</span>'
            f'<span class="ace-glimpse-type">{col_type}</span>'
            f'<span class="ace-glimpse-vals">{sample}</span>'
            f'<span class="ace-glimpse-roles">'
            f'<button type="button" class="ace-role-btn" data-role="id">ID</button>'
            f'<button type="button" class="ace-role-btn" data-role="text">Text</button>'
            f'</span>'
            f'</div>'
        )

    fragment = f"""
    <p class="ace-wizard-q">Select columns</p>
    <form id="import-form" hx-post="/api/import/commit" hx-target="#step-done" hx-swap="innerHTML"
          hx-on::after-request="if(event.detail.successful) showStep('step-done')">
      <div class="ace-glimpse">
        <div class="ace-glimpse-header">
          <span>{filename}</span>
          <span>{n_rows:,} rows &times; {n_cols}</span>
        </div>
        <div class="ace-glimpse-hint">Click to assign: one ID, one or more Text</div>
        {glimpse_rows}
      </div>
      <input type="hidden" name="id_column" id="import-id-col" value="">
      <input type="hidden" name="text_columns" id="import-text-cols" value="">
      <button type="submit" class="ace-btn ace-btn--primary" id="import-submit"
              disabled style="margin-top:12px">Import</button>
    </form>
    <button class="ace-wizard-back" onclick="showStep('step-upload')">&larr; Back</button>

    <script>
    (function() {{
      var form = document.getElementById('import-form');
      if (!form) return;

      form.addEventListener('click', function(e) {{
        var btn = e.target.closest('.ace-role-btn');
        if (!btn) return;
        var row = btn.closest('.ace-glimpse-row');
        var role = btn.dataset.role;
        var wasActive = btn.classList.contains('active');

        if (role === 'id') {{
          // Radio: clear all other IDs
          form.querySelectorAll('.ace-role-btn[data-role="id"].active').forEach(function(b) {{
            b.classList.remove('active');
            b.closest('.ace-glimpse-row').dataset.role = b.closest('.ace-glimpse-row').querySelector('.ace-role-btn[data-role="text"].active') ? 'text' : '';
          }});
          // Clear text on this row if setting ID
          var textBtn = row.querySelector('.ace-role-btn[data-role="text"]');
          if (textBtn) {{ textBtn.classList.remove('active'); }}
        }} else {{
          // Clear ID on this row if setting text
          var idBtn = row.querySelector('.ace-role-btn[data-role="id"]');
          if (idBtn) {{ idBtn.classList.remove('active'); }}
        }}

        if (wasActive) {{
          btn.classList.remove('active');
          row.dataset.role = '';
        }} else {{
          btn.classList.add('active');
          row.dataset.role = role;
        }}

        // Update hidden inputs
        var idRow = form.querySelector('.ace-role-btn[data-role="id"].active');
        document.getElementById('import-id-col').value = idRow ? idRow.closest('.ace-glimpse-row').dataset.col : '';

        var textCols = [];
        form.querySelectorAll('.ace-role-btn[data-role="text"].active').forEach(function(b) {{
          textCols.push(b.closest('.ace-glimpse-row').dataset.col);
        }});
        document.getElementById('import-text-cols').value = textCols.join(',');

        // Enable/disable submit
        document.getElementById('import-submit').disabled = !(idRow && textCols.length);
      }});
    }})();
    </script>
    """
    return HTMLResponse(fragment)


@router.post("/import/commit")
async def import_commit(
    request: Request,
    id_column: str = Form(...),
    text_columns: str = Form(...),
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
        text_col_list = [c.strip() for c in text_columns.split(",") if c.strip()]
        count = import_csv(conn, tmp_path, id_column, text_col_list)
    except Exception as e:
        db_gen.close()
        return _oob_toast(f"Import failed: {e}")
    finally:
        db_gen.close()

    # Clean up temp file
    Path(tmp_path).unlink(missing_ok=True)
    request.app.state.import_tmp_path = None

    return HTMLResponse(
        f'<p class="ace-wizard-count">{count} source{"s" if count != 1 else ""}</p>'
        f'<p style="color:var(--ace-text-muted);margin:0 0 1.5rem">imported successfully</p>'
        f'<a href="/code" class="ace-wizard-action">Start coding &rarr;</a>'
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
        f'<p class="ace-wizard-count">{count} text file{"s" if count != 1 else ""}</p>'
        f'<p style="color:var(--ace-text-muted);margin:0 0 1.5rem">imported successfully</p>'
        f'<a href="/code" class="ace-wizard-action">Start coding &rarr;</a>'
    )
