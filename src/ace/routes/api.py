"""API routes — JSON/HTMX fragment responses."""

from __future__ import annotations

import asyncio
import html
import json
import platform
import re
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, Form, Query, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

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


# ---------------------------------------------------------------------------
# Annotation export
# ---------------------------------------------------------------------------


@router.get("/export/annotations")
async def export_annotations(request: Request):
    """Export all annotations as CSV download."""
    from ace.services.exporter import export_annotations_csv
    from ace.models.project import get_project
    from datetime import datetime

    project_path = getattr(request.app.state, "project_path", None)
    if not project_path:
        return HTMLResponse("No project open", status_code=400)

    conn = sqlite3.connect(project_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        project = get_project(conn)
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
        tmp.close()
        count = export_annotations_csv(conn, tmp.name)
        content = Path(tmp.name).read_text()
        Path(tmp.name).unlink(missing_ok=True)
    finally:
        conn.close()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{project['name']}_annotations_{timestamp}.csv"

    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Coding annotation helpers
# ---------------------------------------------------------------------------


def _get_undo_manager(request: Request):
    """Get or create the UndoManager for the current project."""
    from ace.services.undo import UndoManager

    project_path = request.app.state.project_path
    managers = request.app.state.undo_managers
    if project_path not in managers:
        managers[project_path] = UndoManager()
    return managers[project_path]


def _open_project_db(request: Request) -> sqlite3.Connection:
    """Open a direct SQLite connection to the current project."""
    from ace.db.schema import ACE_APPLICATION_ID

    conn = sqlite3.connect(request.app.state.project_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _render_coding_oob(request: Request, conn, coder_id: str, current_index: int) -> str:
    """Render the full coding workspace via the coding.html template."""
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    ctx = _coding_context(conn, coder_id, current_index)
    ctx["request"] = request

    text_html = render_block(templates.env, "coding.html", "text_panel", ctx)
    ann_html = render_block(templates.env, "coding.html", "annotation_list", ctx)

    return text_html + f'<div id="annotation-list" hx-swap-oob="innerHTML">{ann_html}</div>'


def _render_full_coding_oob(request: Request, conn, coder_id: str, target_index: int) -> str:
    """Render all 6 coding swap zones (primary text_panel + 5 OOB blocks)."""
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    ctx = _coding_context(conn, coder_id, target_index)
    ctx["request"] = request

    primary = render_block(templates.env, "coding.html", "text_panel", ctx)

    oob_blocks = [
        ("source_header", "source-header"),
        ("annotation_list", "annotation-list"),
        ("bottom_bar", "bottom-bar"),
        ("source_grid", "source-grid"),
        ("code_sidebar", "code-sidebar"),
    ]

    parts = [primary]
    for block_name, element_id in oob_blocks:
        block_html = render_block(templates.env, "coding.html", block_name, ctx)
        parts.append(f'<div id="{element_id}" hx-swap-oob="innerHTML">{block_html}</div>')

    return "".join(parts)


def _resolve_source_id(conn, coder_id: str, current_index: int) -> str | None:
    """Get the source_id for the given assignment index."""
    from ace.models.assignment import get_assignments_for_coder

    assignments = get_assignments_for_coder(conn, coder_id)
    if not assignments or current_index >= len(assignments):
        return None
    return assignments[current_index]["source_id"]


# ---------------------------------------------------------------------------
# Coding annotation routes
# ---------------------------------------------------------------------------


@router.post("/code/apply")
async def annotate(
    request: Request,
    code_id: str = Form(...),
    current_index: int = Form(default=0),
    start_offset: int = Form(default=-1),
    end_offset: int = Form(default=-1),
    selected_text: str = Form(default=""),
):
    """Create an annotation and return updated text panel + annotation list."""
    from ace.models.annotation import add_annotation
    from ace.models.assignment import update_assignment_status

    coder_id = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        return HTMLResponse("", status_code=400)

    # If no selection provided, ignore
    if start_offset < 0 or end_offset < 0 or not selected_text:
        return HTMLResponse("", status_code=400)

    conn = _open_project_db(request)
    try:
        source_id = _resolve_source_id(conn, coder_id, current_index)
        if source_id is None:
            return HTMLResponse("", status_code=400)

        ann_id = add_annotation(
            conn, source_id, coder_id, code_id,
            start_offset, end_offset, selected_text,
        )

        # Record for undo
        undo = _get_undo_manager(request)
        undo.record_add(source_id, ann_id)

        # Auto-transition pending -> in_progress
        assignment = conn.execute(
            "SELECT status FROM assignment WHERE source_id = ? AND coder_id = ?",
            (source_id, coder_id),
        ).fetchone()
        if assignment and assignment["status"] == "pending":
            update_assignment_status(conn, source_id, coder_id, "in_progress")

        content = _render_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(content)
    finally:
        conn.close()


@router.post("/code/delete-annotation")
async def delete_annotation_route(
    request: Request,
    annotation_id: str = Form(...),
    current_index: int = Form(default=0),
):
    """Soft-delete an annotation and return updated HTML."""
    from ace.models.annotation import delete_annotation

    coder_id = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        return HTMLResponse("", status_code=400)

    conn = _open_project_db(request)
    try:
        # Look up source_id from the annotation before deleting
        ann_row = conn.execute(
            "SELECT source_id FROM annotation WHERE id = ?",
            (annotation_id,),
        ).fetchone()
        if ann_row is None:
            return HTMLResponse("", status_code=404)

        source_id = ann_row["source_id"]
        delete_annotation(conn, annotation_id)

        # Record for undo
        undo = _get_undo_manager(request)
        undo.record_delete(source_id, annotation_id)

        content = _render_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(content)
    finally:
        conn.close()


@router.post("/code/undo")
async def undo_route(
    request: Request,
    current_index: int = Form(default=0),
):
    """Undo the last annotation action for the current source."""
    from ace.models.annotation import delete_annotation, undelete_annotation

    coder_id = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        return HTMLResponse("", status_code=400)

    conn = _open_project_db(request)
    try:
        source_id = _resolve_source_id(conn, coder_id, current_index)
        if source_id is None:
            return HTMLResponse("", status_code=400)

        undo_mgr = _get_undo_manager(request)
        action = undo_mgr.undo(source_id)
        if action is None:
            return HTMLResponse("", status_code=204)

        if action["type"] == "undo_add":
            delete_annotation(conn, action["annotation_id"])
            msg = "Annotation removed"
        elif action["type"] == "undo_delete":
            undelete_annotation(conn, action["annotation_id"])
            msg = "Annotation restored"
        else:
            msg = "Undo"

        content = _render_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(
            content,
            headers={"HX-Trigger": f'{{"ace-toast": "{msg}"}}'},
        )
    finally:
        conn.close()


@router.post("/code/redo")
async def redo_route(
    request: Request,
    current_index: int = Form(default=0),
):
    """Redo the last undone annotation action for the current source."""
    from ace.models.annotation import delete_annotation, undelete_annotation

    coder_id = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        return HTMLResponse("", status_code=400)

    conn = _open_project_db(request)
    try:
        source_id = _resolve_source_id(conn, coder_id, current_index)
        if source_id is None:
            return HTMLResponse("", status_code=400)

        undo_mgr = _get_undo_manager(request)
        action = undo_mgr.redo(source_id)
        if action is None:
            return HTMLResponse("", status_code=204)

        if action["type"] == "redo_add":
            undelete_annotation(conn, action["annotation_id"])
            msg = "Annotation re-applied"
        elif action["type"] == "redo_delete":
            delete_annotation(conn, action["annotation_id"])
            msg = "Annotation re-removed"
        else:
            msg = "Redo"

        content = _render_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(
            content,
            headers={"HX-Trigger": f'{{"ace-toast": "{msg}"}}'},
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Source navigation + flag routes
# ---------------------------------------------------------------------------


@router.post("/code/navigate")
async def navigate_route(
    request: Request,
    current_index: int = Form(default=0),
    target_index: int = Form(default=0),
):
    """Navigate between sources, auto-completing/starting assignments."""
    import json

    from ace.models.assignment import get_assignments_for_coder, update_assignment_status

    coder_id = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        return HTMLResponse("", status_code=400)

    conn = _open_project_db(request)
    try:
        assignments = get_assignments_for_coder(conn, coder_id)
        if not assignments:
            return HTMLResponse("", status_code=400)

        total = len(assignments)

        # Clamp target
        if target_index < 0:
            target_index = 0
        if target_index >= total:
            target_index = total - 1

        # Auto-complete departing source
        if 0 <= current_index < total:
            if assignments[current_index]["status"] == "in_progress":
                source_id = assignments[current_index]["source_id"]
                update_assignment_status(conn, source_id, coder_id, "complete")

        # Auto-start arriving source
        if assignments[target_index]["status"] == "pending":
            source_id = assignments[target_index]["source_id"]
            update_assignment_status(conn, source_id, coder_id, "in_progress")

        content = _render_full_coding_oob(request, conn, coder_id, target_index)
        trigger = json.dumps({"ace-navigate": {"index": target_index, "total": total}})
        return HTMLResponse(content, headers={"HX-Trigger": trigger})
    finally:
        conn.close()


@router.post("/code/flag")
async def flag_route(
    request: Request,
    source_index: int = Form(default=0),
):
    """Toggle the flagged status of the current source."""
    from ace.models.assignment import get_assignments_for_coder, update_assignment_status

    coder_id = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        return HTMLResponse("", status_code=400)

    conn = _open_project_db(request)
    try:
        assignments = get_assignments_for_coder(conn, coder_id)
        if not assignments or source_index >= len(assignments):
            return HTMLResponse("", status_code=400)

        assignment = assignments[source_index]
        source_id = assignment["source_id"]
        current_status = assignment["status"]

        new_status = "in_progress" if current_status == "flagged" else "flagged"
        update_assignment_status(conn, source_id, coder_id, new_status)

        content = _render_full_coding_oob(request, conn, coder_id, source_index)
        return HTMLResponse(content)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Codebook CRUD helpers
# ---------------------------------------------------------------------------


def _render_code_sidebar(request: Request, conn, coder_id: str, current_index: int) -> str:
    """Render just the code sidebar block."""
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    ctx = _coding_context(conn, coder_id, current_index)
    ctx["request"] = request
    return render_block(templates.env, "coding.html", "code_sidebar", ctx)


def _render_sidebar_and_text(request: Request, conn, coder_id: str, current_index: int) -> str:
    """Render code sidebar (primary) + OOB text panel + OOB code-colours style."""
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    ctx = _coding_context(conn, coder_id, current_index)
    ctx["request"] = request

    sidebar_html = render_block(templates.env, "coding.html", "code_sidebar", ctx)
    text_html = render_block(templates.env, "coding.html", "text_panel", ctx)

    # Regenerate code-colours CSS inline (not a named block in the template)
    colour_css_parts = []
    for code in ctx["codes"]:
        hex_col = code["colour"]
        r = int(hex_col[1:3], 16)
        g = int(hex_col[3:5], 16)
        b = int(hex_col[5:7], 16)
        colour_css_parts.append(
            f".ace-code-{code['id']} {{ background-color: rgba({r}, {g}, {b}, var(--ace-annotation-alpha)); }}"
        )
    colours_css = "\n".join(colour_css_parts)

    return (
        sidebar_html
        + f'<div id="text-panel" hx-swap-oob="innerHTML">{text_html}</div>'
        + f'<style id="code-colours" hx-swap-oob="innerHTML">{colours_css}</style>'
    )


# ---------------------------------------------------------------------------
# Codebook CRUD routes
# ---------------------------------------------------------------------------


@router.post("/codes")
async def create_code(
    request: Request,
    name: str = Form(...),
    current_index: int = Form(default=0),
):
    """Create a new code and return updated sidebar."""
    from ace.models.codebook import add_code, list_codes, next_colour

    coder_id = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        return HTMLResponse("", status_code=400)

    name = name.strip()
    if not name:
        return _oob_toast("Code name cannot be empty.")

    conn = _open_project_db(request)
    try:
        existing = list_codes(conn)
        colour = next_colour(len(existing))
        add_code(conn, name, colour)
        content = _render_code_sidebar(request, conn, coder_id, current_index)
        return HTMLResponse(content)
    finally:
        conn.close()


@router.post("/codes/reorder")
async def reorder_codes_route(
    request: Request,
    code_ids: str = Form(...),
    current_index: int = Form(default=0),
):
    """Reorder codes and return updated sidebar."""
    from ace.models.codebook import reorder_codes

    coder_id = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        return HTMLResponse("", status_code=400)

    try:
        ids_list = json.loads(code_ids)
    except (json.JSONDecodeError, TypeError):
        return _oob_toast("Invalid code_ids format.")

    conn = _open_project_db(request)
    try:
        reorder_codes(conn, ids_list)
        content = _render_code_sidebar(request, conn, coder_id, current_index)
        return HTMLResponse(content)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Codebook import / export  (registered before {code_id} to avoid path clash)
# ---------------------------------------------------------------------------


@router.get("/codes/export")
async def export_codebook(request: Request):
    """Export the codebook as a CSV file download."""
    from ace.models.codebook import export_codebook_to_csv

    conn = _open_project_db(request)
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        tmp.close()
        export_codebook_to_csv(conn, tmp.name)
    finally:
        conn.close()

    return FileResponse(
        tmp.name,
        media_type="text/csv",
        filename="codebook.csv",
    )


@router.post("/codes/import/preview")
async def import_codebook_preview(request: Request, file: UploadFile = File(...)):
    """Upload a codebook CSV and return a preview dialog."""
    from ace.models.codebook import preview_codebook_csv

    data = await file.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    try:
        tmp.write(data)
        tmp.close()

        conn = _open_project_db(request)
        try:
            previewed = preview_codebook_csv(conn, tmp.name)
        finally:
            conn.close()
    except Exception as e:
        Path(tmp.name).unlink(missing_ok=True)
        return _oob_toast(f"Could not parse codebook CSV: {e}")

    # Store temp path for the import step
    request.app.state.codebook_import_tmp = tmp.name

    # Build preview rows
    rows_html = ""
    for code in previewed:
        esc_name = html.escape(code["name"])
        esc_colour = html.escape(code["colour"])
        esc_group = html.escape(code.get("group_name") or "")
        exists = code["exists"]
        checked = "" if exists else "checked"
        disabled = "disabled" if exists else ""
        opacity = "opacity:0.5" if exists else ""
        label_extra = " (already exists)" if exists else ""
        rows_html += (
            f'<label style="display:flex;align-items:center;gap:8px;padding:4px 0;{opacity}">'
            f'<input type="checkbox" name="selected" value="{esc_name}" {checked} {disabled}>'
            f'<span class="ace-code-dot" style="background:{esc_colour};width:12px;height:12px;'
            f'border-radius:50%;display:inline-block;flex-shrink:0"></span>'
            f'<span>{esc_name}{label_extra}</span>'
            f'</label>'
        )

    return HTMLResponse(
        f'<dialog>'
        f'<h3 style="font-size:15px;font-weight:500;margin:0 0 16px">Import Codebook</h3>'
        f'<div style="max-height:300px;overflow-y:auto">{rows_html}</div>'
        f'<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">'
        f'<button type="button" class="ace-btn" onclick="this.closest(\'dialog\').close()">Cancel</button>'
        f'<button type="button" class="ace-btn ace-btn--primary" '
        f'id="codebook-import-btn" '
        f'onclick="aceImportCodebook(this)">Import</button>'
        f'</div>'
        f'</dialog>'
    )


@router.post("/codes/import")
async def import_codebook(
    request: Request,
    codes_json: str = Form(...),
    current_index: int = Form(default=0),
):
    """Import selected codes from a previously previewed CSV."""
    from ace.models.codebook import import_selected_codes

    coder_id = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        return HTMLResponse("", status_code=400)

    try:
        codes_list = json.loads(codes_json)
    except (json.JSONDecodeError, TypeError):
        return _oob_toast("Invalid codes_json format.")

    conn = _open_project_db(request)
    try:
        import_selected_codes(conn, codes_list)
        content = _render_code_sidebar(request, conn, coder_id, current_index)
    finally:
        conn.close()

    # Clean up temp file
    tmp_path = getattr(request.app.state, "codebook_import_tmp", None)
    if tmp_path:
        Path(tmp_path).unlink(missing_ok=True)
        request.app.state.codebook_import_tmp = None

    return HTMLResponse(content)


# ---------------------------------------------------------------------------
# Codebook {code_id} routes
# ---------------------------------------------------------------------------


@router.put("/codes/{code_id}")
async def update_code_route(
    request: Request,
    code_id: str,
    name: str | None = Form(default=None),
    colour: str | None = Form(default=None),
    group_name: str | None = Form(default=None),
    current_index: int = Form(default=0),
):
    """Update a code (rename, recolour, move group) and return sidebar + text panel."""
    from ace.models.codebook import update_code

    coder_id = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        return HTMLResponse("", status_code=400)

    # Validate colour if provided
    if colour is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", colour):
        return _oob_toast("Invalid colour format. Use #RRGGBB.")

    conn = _open_project_db(request)
    try:
        kwargs: dict = {}
        if name is not None:
            kwargs["name"] = name.strip()
        if colour is not None:
            kwargs["colour"] = colour
        if group_name is not None:
            kwargs["group_name"] = group_name

        update_code(conn, code_id, **kwargs)
        content = _render_sidebar_and_text(request, conn, coder_id, current_index)
        return HTMLResponse(content)
    finally:
        conn.close()


@router.delete("/codes/{code_id}")
async def delete_code_route(
    request: Request,
    code_id: str,
    current_index: int = Query(default=0),
):
    """Delete a code (cascades annotations) and return sidebar + text panel."""
    from ace.models.codebook import delete_code

    coder_id = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        return HTMLResponse("", status_code=400)

    conn = _open_project_db(request)
    try:
        delete_code(conn, code_id)
        content = _render_sidebar_and_text(request, conn, coder_id, current_index)
        return HTMLResponse(content)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dialog endpoints
# ---------------------------------------------------------------------------


@router.get("/codes/{code_id}/rename-dialog")
async def rename_dialog(request: Request, code_id: str):
    """Return a rename dialog for the given code."""
    conn = _open_project_db(request)
    try:
        row = conn.execute(
            "SELECT name FROM codebook_code WHERE id = ?", (code_id,)
        ).fetchone()
        if row is None:
            return HTMLResponse("", status_code=404)
        current_name = html.escape(row["name"])
    finally:
        conn.close()

    return HTMLResponse(
        f'<dialog>'
        f'<h3 style="font-size:15px;font-weight:500;margin:0 0 16px">Rename Code</h3>'
        f'<form hx-put="/api/codes/{code_id}" hx-target="#code-sidebar" hx-swap="innerHTML">'
        f'<input type="text" name="name" value="{current_name}" '
        f'class="ace-input" style="width:100%" autocomplete="off">'
        f'<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">'
        f'<button type="button" class="ace-btn" onclick="this.closest(\'dialog\').close()">Cancel</button>'
        f'<button type="submit" class="ace-btn ace-btn--primary" '
        f'onclick="this.closest(\'dialog\').close()">Rename</button>'
        f'</div>'
        f'</form>'
        f'</dialog>'
    )


@router.get("/codes/{code_id}/colour-dialog")
async def colour_dialog(request: Request, code_id: str):
    """Return a colour picker dialog with palette swatches."""
    from ace.models.codebook import COLOUR_PALETTE

    swatches = ""
    for hex_val, _ in COLOUR_PALETTE:
        swatches += (
            f'<button type="button" class="ace-colour-swatch" '
            f'style="background:{hex_val};width:28px;height:28px;border-radius:4px;border:1px solid #bdbdbd;cursor:pointer;padding:0" '
            f'hx-put="/api/codes/{code_id}" '
            f"""hx-vals='{{"colour":"{hex_val}"}}' """
            f'hx-target="#code-sidebar" hx-swap="innerHTML" '
            f'onclick="this.closest(\'dialog\').close()"></button>'
        )

    return HTMLResponse(
        f'<dialog>'
        f'<h3 style="font-size:15px;font-weight:500;margin:0 0 16px">Choose Colour</h3>'
        f'<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:6px">'
        f'{swatches}'
        f'</div>'
        f'<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">'
        f'<button type="button" class="ace-btn" onclick="this.closest(\'dialog\').close()">Cancel</button>'
        f'</div>'
        f'</dialog>'
    )


@router.get("/codes/{code_id}/delete-dialog")
async def delete_dialog(request: Request, code_id: str):
    """Return a confirmation dialog for deleting a code."""
    conn = _open_project_db(request)
    try:
        row = conn.execute(
            "SELECT name FROM codebook_code WHERE id = ?", (code_id,)
        ).fetchone()
        if row is None:
            return HTMLResponse("", status_code=404)
        code_name = html.escape(row["name"])

        ann_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM annotation WHERE code_id = ? AND deleted_at IS NULL",
            (code_id,),
        ).fetchone()["cnt"]

        source_count = conn.execute(
            "SELECT COUNT(DISTINCT source_id) AS cnt FROM annotation WHERE code_id = ? AND deleted_at IS NULL",
            (code_id,),
        ).fetchone()["cnt"]
    finally:
        conn.close()

    if ann_count > 0:
        warning = (
            f"This will remove {ann_count} annotation{'s' if ann_count != 1 else ''} "
            f"across {source_count} source{'s' if source_count != 1 else ''}."
        )
    else:
        warning = "This code has no annotations."

    return HTMLResponse(
        f'<dialog>'
        f'<h3 style="font-size:15px;font-weight:500;margin:0 0 16px">Delete {code_name}?</h3>'
        f'<p style="margin:0 0 16px;color:var(--ace-text-muted)">{warning}</p>'
        f'<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">'
        f'<button type="button" class="ace-btn" onclick="this.closest(\'dialog\').close()">Cancel</button>'
        f'<button type="button" class="ace-btn ace-btn--danger" '
        f'hx-delete="/api/codes/{code_id}" '
        f'hx-target="#code-sidebar" hx-swap="innerHTML" '
        f'onclick="this.closest(\'dialog\').close()">Delete</button>'
        f'</div>'
        f'</dialog>'
    )


@router.get("/codes/{code_id}/move-dialog")
async def move_dialog(request: Request, code_id: str):
    """Return a dialog for moving a code to a group."""
    conn = _open_project_db(request)
    try:
        row = conn.execute(
            "SELECT name, group_name FROM codebook_code WHERE id = ?", (code_id,)
        ).fetchone()
        if row is None:
            return HTMLResponse("", status_code=404)
        code_name = html.escape(row["name"])
        current_group = row["group_name"]

        groups = conn.execute(
            "SELECT DISTINCT group_name FROM codebook_code "
            "WHERE group_name IS NOT NULL ORDER BY group_name"
        ).fetchall()
        group_names = [g["group_name"] for g in groups]
    finally:
        conn.close()

    options = ""

    # Ungrouped option
    active = ' style="font-weight:600"' if current_group is None else ""
    options += (
        f'<button type="button" class="ace-btn" style="width:100%;text-align:left;margin-bottom:4px"'
        f' hx-put="/api/codes/{code_id}"'
        f""" hx-vals='{{"group_name":""}}'"""
        f' hx-target="#code-sidebar" hx-swap="innerHTML"'
        f' onclick="this.closest(\'dialog\').close()"'
        f'{active}>Ungrouped</button>'
    )

    # Existing groups
    for gn in group_names:
        esc_gn = html.escape(gn)
        active = ' style="font-weight:600"' if gn == current_group else ""
        options += (
            f'<button type="button" class="ace-btn" style="width:100%;text-align:left;margin-bottom:4px"'
            f' hx-put="/api/codes/{code_id}"'
            f""" hx-vals='{{"group_name":"{esc_gn}"}}'"""
            f' hx-target="#code-sidebar" hx-swap="innerHTML"'
            f' onclick="this.closest(\'dialog\').close()"'
            f'{active}>{esc_gn}</button>'
        )

    return HTMLResponse(
        f'<dialog>'
        f'<h3 style="font-size:15px;font-weight:500;margin:0 0 16px">Move {code_name} to Group</h3>'
        f'<div style="display:flex;flex-direction:column">'
        f'{options}'
        f'</div>'
        f'<details style="margin-top:8px">'
        f'<summary style="cursor:pointer;font-size:13px;color:var(--ace-text-muted)">New Group\u2026</summary>'
        f'<form hx-put="/api/codes/{code_id}" hx-target="#code-sidebar" hx-swap="innerHTML" '
        f'style="display:flex;gap:8px;margin-top:8px">'
        f'<input type="text" name="group_name" placeholder="Group name" '
        f'class="ace-input" style="flex:1" autocomplete="off">'
        f'<button type="submit" class="ace-btn ace-btn--primary" '
        f'onclick="this.closest(\'dialog\').close()">Move</button>'
        f'</form>'
        f'</details>'
        f'<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">'
        f'<button type="button" class="ace-btn" onclick="this.closest(\'dialog\').close()">Cancel</button>'
        f'</div>'
        f'</dialog>'
    )
