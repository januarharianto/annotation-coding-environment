"""API routes — JSON/HTMX fragment responses."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import platform
import re
import sqlite3
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _require_coder(request: Request) -> str:
    """Return coder_id from app state; raise HTTP 400 if not set.

    Used by every route that mutates coder-owned state. The single
    remaining caller that wants Optional semantics (the `codes`
    listing route) reads `request.app.state.coder_id` directly.
    """
    cid = getattr(request.app.state, "coder_id", None)
    if cid is None:
        raise HTTPException(status_code=400)
    return cid


def _safe_filename(name: str) -> str:
    """Sanitise a string for use in HTTP Content-Disposition filename.

    HTTP header values are ASCII/latin-1 only, and the filename attribute
    is vulnerable to header injection via CR/LF and parsing ambiguity from
    quotes/semicolons/backslashes. Collapses everything except alphanum,
    dot, dash, underscore, and space into underscores.
    """
    return re.sub(r"[^A-Za-z0-9._\- ]", "_", name)


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


def _accept_to_filetypes(accept: str | None) -> list[tuple[str, str]]:
    """Convert an accept filter like ".ace,.csv" to tkinter filetypes."""
    if not accept:
        return []
    extensions = [ext.strip() for ext in accept.split(",") if ext.strip()]
    types = []
    for ext in extensions:
        ext = ext if ext.startswith(".") else f".{ext}"
        types.append((f"{ext.lstrip('.')} files", f"*{ext}"))
    return types


def _run_osascript(script: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _tk_root():
    """Create a hidden topmost tkinter root for file dialogs."""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def _tk_pick_file(filetypes: list[tuple[str, str]] | None = None) -> str:
    from tkinter import filedialog
    root = _tk_root()
    path = filedialog.askopenfilename(filetypes=filetypes or [])
    root.destroy()
    return path or ""


def _tk_pick_folder() -> str:
    from tkinter import filedialog
    root = _tk_root()
    path = filedialog.askdirectory()
    root.destroy()
    return path or ""


def _tk_pick_files(filetypes: list[tuple[str, str]] | None = None) -> list[str]:
    from tkinter import filedialog
    root = _tk_root()
    paths = filedialog.askopenfilenames(filetypes=filetypes or [])
    root.destroy()
    return list(paths)


# ---------------------------------------------------------------------------
# Native file picker endpoints
# ---------------------------------------------------------------------------

@router.post("/native/pick-file")
async def pick_file(accept: str | None = Form(default=None)):
    """Open a native file picker and return the selected path."""
    if platform.system() == "Darwin":
        type_filter = _accept_to_types(accept)
        script = f'POSIX path of (choose file{type_filter})'
        result = await asyncio.to_thread(_run_osascript, script)
        path = result.stdout.strip() if result.returncode == 0 else ""
    else:
        filetypes = _accept_to_filetypes(accept)
        path = await asyncio.to_thread(_tk_pick_file, filetypes)
    return JSONResponse({"path": path})


@router.post("/native/pick-folder")
async def pick_folder():
    """Open a native folder picker and return the selected path."""
    if platform.system() == "Darwin":
        script = 'POSIX path of (choose folder)'
        result = await asyncio.to_thread(_run_osascript, script)
        path = result.stdout.strip() if result.returncode == 0 else ""
    else:
        path = await asyncio.to_thread(_tk_pick_folder)
    return JSONResponse({"path": path})


@router.post("/native/pick-files")
async def pick_files(accept: str | None = Form(default=None)):
    """Open a native file picker (multiple selection) and return paths."""
    if platform.system() == "Darwin":
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
        paths = [p for p in result.stdout.strip().split("\n") if p] if result.returncode == 0 else []
    else:
        filetypes = _accept_to_filetypes(accept)
        paths = await asyncio.to_thread(_tk_pick_files, filetypes)
    return JSONResponse({"paths": paths})


# ---------------------------------------------------------------------------
# Import preview fragment helper
# ---------------------------------------------------------------------------

def _preview_fragment(filename: str, snippet: str, escaped_folder: str) -> str:
    """Return the #import-preview HTML fragment (outerHTML-swappable)."""
    escaped_fn = html.escape(filename)
    escaped_snippet = html.escape(snippet)
    return (
        f'<div id="import-preview">'
        f'<div style="display:flex;align-items:center;justify-content:center;gap:8px;margin-bottom:8px;">'
        f'<span style="font-size:var(--ace-font-size-2xs);color:var(--ace-text-muted);'
        f'text-transform:uppercase;letter-spacing:0.5px;">Preview — {escaped_fn}</span>'
        f'<button hx-get="/api/import/preview?folder={escaped_folder}" hx-target="#import-preview"'
        f' hx-swap="outerHTML" style="background:none;border:1px solid var(--ace-border);'
        f'border-radius:4px;padding:2px 6px;cursor:pointer;font-size:var(--ace-font-size-2xs);'
        f'color:var(--ace-text-muted);" title="Preview another file">&#x21BB;</button>'
        f'</div>'
        f'<p style="text-align:left;font-size:var(--ace-font-size-md);color:var(--ace-text);'
        f'margin:0;line-height:1.5;display:-webkit-box;-webkit-line-clamp:4;'
        f'-webkit-box-orient:vertical;overflow:hidden;">{escaped_snippet}</p>'
        f'</div>'
    )


def _oob_announce(message: str, assertive: bool = False) -> str:
    """Return an OOB-swap fragment that writes to an ARIA live region.

    Screen readers announce polite by default; pass assertive=True for errors
    that should interrupt the user's flow. Returns a string fragment that a
    caller can concatenate to their existing HTML response body.
    """
    escaped = html.escape(message)
    target_id = "ace-live-region-assertive" if assertive else "ace-live-region"
    role = 'role="alert" ' if assertive else ""
    aria = "assertive" if assertive else "polite"
    return (
        f'<div {role}aria-live="{aria}" class="ace-sr-only" '
        f'id="{target_id}" hx-swap-oob="innerHTML">{escaped}</div>'
    )


def _with_headers(response: HTMLResponse, headers: dict[str, str]) -> HTMLResponse:
    """Mutate-and-return: merge headers onto an existing HTMLResponse."""
    for k, v in headers.items():
        response.headers[k] = v
    return response


def _oob_status_undo(message: str) -> str:
    """OOB-swap status with an inline [Z] undo keycap — for soft-delete actions.

    Returns the raw HTML string (not HTMLResponse) so callers can concatenate
    it with other OOB fragments before wrapping. Only emits the statusbar
    fragment + ARIA announce — the text-panel pill on /code is populated
    client-side by bridge.js (its DOM lives inside #text-panel, so an OOB
    swap to it would be clobbered by the primary swap that re-renders the
    text panel). Keycap is a real button so mouse users have a click target;
    pressing Z on the keyboard fires the same /api/undo path via bridge.js.
    """
    escaped = html.escape(message)
    inner = (
        f'<span class="ace-statusbar-undo-msg">{escaped}</span>'
        '<span class="ace-statusbar-undo-sep">·</span>'
        '<button type="button" class="ace-statusbar-undo" '
        'data-ace-undo-affordance="1" aria-label="Undo (Z)">'
        '<span class="ace-statusbar-undo-keycap">Z</span>'
        '<span>undo</span>'
        '</button>'
    )
    status_fragment = (
        '<span class="ace-statusbar-event ace-statusbar-event--undo" '
        'id="ace-statusbar-event" hx-swap-oob="outerHTML">' + inner + '</span>'
    )
    announce = _oob_announce(message, assertive=False)
    return status_fragment + announce


def _oob_status(message: str, kind: str = "err") -> HTMLResponse:
    """Return OOB-swap fragments that set the event channel on all pages.

    Emits three fragments:
      1. Statusbar event span (visible on /, /import, /agreement — hidden by
         CSS on /code but still DOM-present).
      2. Text-panel event pill (only exists on /code — HTMX silently drops
         the fragment on other pages).
      3. Assertive ARIA live region (because the statusbar and pill are
         aria-hidden / role=status, so screen-reader users would otherwise
         miss errors).

    kind is "err" for sticky errors, "ok" for 2-second ephemeral success
    (client-side timer in _setStatus clears ok pills).
    """
    escaped = html.escape(message)
    status_fragment = (
        f'<span class="ace-statusbar-event ace-statusbar-event--{kind}" '
        f'id="ace-statusbar-event" hx-swap-oob="outerHTML">{escaped}</span>'
    )
    # Same message, second target — only present on /code.
    pill_fragment = (
        f'<span class="ace-text-event-pill ace-text-event-pill--{kind}" '
        f'id="ace-text-event-pill" role="status" aria-live="polite" '
        f'hx-swap-oob="outerHTML">{escaped}</span>'
    )
    # Assertive region for errors (sticky), polite for ok (ephemeral).
    announce = _oob_announce(message, assertive=(kind == "err"))
    return HTMLResponse(status_fragment + pill_fragment + announce)


# ---------------------------------------------------------------------------
# Project create / open
# ---------------------------------------------------------------------------

@router.post("/project/create")
async def project_create(
    request: Request,
    name: str = Form(...),
    path: str = Form(...),
    overwrite: bool = Form(default=False),
    coder_name: str = Form(default="default"),
):
    """Create a new .ace project file."""
    from ace.db.connection import create_project
    from ace.models.project import list_coders

    file_path = Path(path)

    # Ensure the path ends with .ace
    if file_path.suffix != ".ace":
        file_path = file_path.with_suffix(".ace")

    try:
        if file_path.exists() and not overwrite:
            # Return an overwrite confirmation dialog
            esc_name = html.escape(name, quote=True)
            esc_coder = html.escape(coder_name, quote=True)
            return HTMLResponse(
                '<dialog class="ace-dialog">'
                "<p>This file already exists. Overwrite it?</p>"
                '<form method="dialog" style="display:flex;gap:0.5rem;margin-top:1rem;justify-content:flex-end">'
                '<button class="ace-btn" onclick="this.closest(\'dialog\').remove()" type="button">Cancel</button>'
                f'<button class="ace-btn ace-btn--danger" '
                f'hx-post="/api/project/create" '
                f'hx-vals=\'{{"name":"{esc_name}","path":"{file_path}","overwrite":"true","coder_name":"{esc_coder}"}}\' '
                f'hx-target="#modal-container" '
                f'hx-swap="innerHTML"'
                f">Overwrite</button>"
                "</form>"
                "</dialog>"
            )

        if file_path.exists() and overwrite:
            file_path.unlink()

        conn = create_project(str(file_path), name, coder_name=coder_name)
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
        return _oob_status(f"Failed to create project: {e}")


@router.post("/project/open")
async def project_open(request: Request, path: str = Form(...)):
    """Open an existing .ace project file."""
    from ace.db.connection import open_project
    from ace.models.project import list_coders
    from ace.models.source import list_sources

    try:
        conn = open_project(path)
    except (ValueError, FileNotFoundError, sqlite3.DatabaseError) as e:
        return _oob_status(str(e))

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
    from ace.services.importer import read_tabular

    # Read the uploaded file into a temp file
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        return _oob_status("File exceeds 50 MB limit")

    suffix = Path(file.filename or "upload.csv").suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.close()

        rows, columns = read_tabular(Path(tmp.name))
    except Exception as e:
        Path(tmp.name).unlink(missing_ok=True)
        return _oob_status(f"Could not parse file: {e}")

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
    glimpse_parts = []
    for col in columns:
        col_type = _infer_type(col)
        sample = _sample_values(col)
        esc_col = html.escape(str(col))
        glimpse_parts.append(
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
    glimpse_rows = "".join(glimpse_parts)

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
        return _oob_status("No uploaded file found. Please upload again.")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        text_col_list = [c.strip() for c in text_columns.split(",") if c.strip()]
        count = import_csv(conn, tmp_path, id_column, text_col_list)
    except Exception as e:
        db_gen.close()
        return _oob_status(f"Import failed: {e}")
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
    """Import .txt and .md files from a folder."""
    from ace.app import get_db
    from ace.services.importer import import_text_files, get_random_preview

    folder = Path(path)
    if not folder.is_dir():
        return _oob_status("Invalid folder path.")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        count = import_text_files(conn, folder)
    except Exception as e:
        db_gen.close()
        return _oob_status(f"Import failed: {e}")
    finally:
        db_gen.close()

    folder_name = html.escape(folder.name)
    escaped_path = html.escape(quote(str(folder), safe=""))

    result = get_random_preview(folder)
    if result:
        filename, snippet = result
        preview_html = (
            f'<div style="border:1px solid var(--ace-border-light);border-radius:8px;padding:16px;'
            f'margin:0 auto 24px;max-width:400px;background:var(--ace-bg-muted);">'
            f'{_preview_fragment(filename, snippet, escaped_path)}'
            f'</div>'
        )
    else:
        preview_html = ""

    return HTMLResponse(
        f'<p class="ace-wizard-count">{count} text file{"s" if count != 1 else ""}</p>'
        f'<p style="color:var(--ace-text-muted);margin:0 0 4px">imported successfully</p>'
        f'<p style="font-size:var(--ace-font-size-md);color:var(--ace-text-muted);margin:0 0 24px">'
        f'from <span style="font-family:var(--ace-font-mono);font-size:var(--ace-font-size-xs);'
        f'background:var(--ace-bg-muted);padding:2px 6px;border-radius:4px;">{folder_name}/</span></p>'
        f'{preview_html}'
        f'<a href="/code" class="ace-wizard-action">Start coding &rarr;</a>'
    )


@router.get("/import/preview")
async def import_preview(folder: str = Query(...)):
    """Return an HTML fragment previewing a random text file from the folder."""
    from ace.services.importer import get_random_preview

    folder_path = Path(folder)
    if not folder_path.is_dir():
        return HTMLResponse('<p style="color:var(--ace-text-muted)">Invalid folder.</p>')

    result = get_random_preview(folder_path)
    if result is None:
        return HTMLResponse('<p style="color:var(--ace-text-muted)">No text files found.</p>')

    filename, snippet = result
    escaped_folder = html.escape(quote(folder, safe=""))
    return HTMLResponse(_preview_fragment(filename, snippet, escaped_folder))


# ---------------------------------------------------------------------------
# CSV-download helper + annotation/notes exports
# ---------------------------------------------------------------------------


def _csv_download(
    request: Request,
    suffix: str,
    write_csv,
) -> Response:
    """Run `write_csv(conn, tmp_path)` against the project db, read the
    resulting CSV back and return it as an attachment download named
    `<project>_<suffix>_<timestamp>.csv`.

    Shared by the annotations and notes export routes — both follow the
    same open-db / write-to-tempfile / read-back / delete flow.
    """
    from datetime import datetime

    from ace.models.project import get_project

    with _project_db(request) as conn:
        project = get_project(conn)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        tmp.close()
        tmp_path = Path(tmp.name)
        try:
            write_csv(conn, tmp.name)
            content = tmp_path.read_text(encoding="utf-8")
        finally:
            tmp_path.unlink(missing_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = _safe_filename(f"{project['name']}_{suffix}_{timestamp}.csv")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/annotations")
async def export_annotations(request: Request):
    """Export all annotations as CSV download."""
    from ace.services.exporter import export_annotations_csv

    return _csv_download(request, "annotations", export_annotations_csv)


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


@contextmanager
def _project_db(request: Request) -> Iterator[sqlite3.Connection]:
    """Context-manager form: yields a direct SQLite connection to the
    current project and closes it on exit.

    Replaces the old `_open_project_db` + `try/finally: conn.close()`
    scaffold that appeared at ~20 call sites.
    """
    conn = sqlite3.connect(request.app.state.project_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
    finally:
        conn.close()


def _hex_to_rgb(hex_col: str) -> tuple[int, int, int]:
    return int(hex_col[1:3], 16), int(hex_col[3:5], 16), int(hex_col[5:7], 16)


def _inject_oob(html: str, element_id: str) -> str:
    return html.replace(f'id="{element_id}"', f'id="{element_id}" hx-swap-oob="outerHTML"', 1)


def _render_colour_style_oob(codes: list[dict]) -> str:
    """Generate <style> block with per-code CSS classes and SVG rect fill rules.

    Emits three rules per code:
    - .ace-code-{cid}: background-color for sidebar dots and bottom chip colours
    - rect.ace-hl-{cid}: fill for annotation highlight rects in the SVG overlay
    - rect.ace-flash-{cid}: fill for temporary chip-click flash rects
    """
    parts = []
    for code in codes:
        r, g, b = _hex_to_rgb(code["colour"])
        cid = code["id"]
        parts.append(
            f".ace-code-{cid} {{"
            f" background-color: rgba({r},{g},{b},var(--ace-annotation-alpha)); }}"
        )
        parts.append(
            f"rect.ace-hl-{cid} {{"
            f" fill: rgba({r},{g},{b},0.30); }}"
        )
        parts.append(
            f"rect.ace-flash-{cid} {{"
            f" fill: rgba({r},{g},{b},0.70); }}"
        )
    return f'<style id="code-colours" hx-swap-oob="outerHTML">{chr(10).join(parts)}</style>'


def _render_ann_data_oob(ctx: dict) -> str:
    """Generate OOB div with annotation data for the SVG highlight overlay."""
    ann_json = ctx.get("annotation_highlights_json", "[]")
    return f'<div id="ace-ann-data" class="ace-hidden" data-annotations="{ann_json}" hx-swap-oob="outerHTML"></div>'


def _render_sources_data_oob(ctx: dict) -> str:
    """Emit an OOB-swap <script> blob with the sources_json payload so the
    client's sparkline + tile grid can re-render after an annotation change.
    """
    # Inside <script type="application/json"> HTML character refs are NOT decoded,
    # so html.escape would break JSON.parse at runtime. Use JSON \uXXXX escapes
    # for < > & — still valid JSON, can't terminate the tag early.
    payload = (
        json.dumps(ctx.get("sources_json", []))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return (
        '<script id="ace-sources-data" type="application/json" '
        f'hx-swap-oob="outerHTML">{payload}</script>'
    )


def _render_full_coding_oob(request: Request, conn, coder_id: str, target_index: int) -> str:
    """Render all coding swap zones."""
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    project_path = request.app.state.project_path
    ctx = _coding_context(conn, coder_id, target_index, project_path=project_path)
    ctx["request"] = request

    primary = render_block(templates.env, "coding.html", "text_panel", ctx)

    oob_blocks = [
        ("code_sidebar", "code-sidebar"),
    ]

    parts = [primary]
    for block_name, element_id in oob_blocks:
        block_html = render_block(templates.env, "coding.html", block_name, ctx)
        parts.append(_inject_oob(block_html, element_id))

    parts.append(_render_colour_style_oob(ctx["codes"]))
    parts.append(_render_ann_data_oob(ctx))
    parts.append(_render_sources_data_oob(ctx))
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
    from ace.models.annotation import add_annotation_merging

    coder_id = _require_coder(request)

    # If no selection provided, ignore
    if start_offset < 0 or end_offset < 0 or not selected_text:
        return HTMLResponse("", status_code=400)

    with _project_db(request) as conn:
        source_id = _resolve_source_id(conn, coder_id, current_index)
        if source_id is None:
            return HTMLResponse("", status_code=400)

        ann_id, replaced_ids = add_annotation_merging(
            conn, source_id, coder_id, code_id,
            start_offset, end_offset, selected_text,
        )

        # Record for undo — compound if any existing annotations were merged
        undo = _get_undo_manager(request)
        if replaced_ids:
            undo.record_merge_add(source_id, ann_id, replaced_ids)
        else:
            undo.record_add(source_id, ann_id)

        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(content)


@router.post("/code/delete-annotation")
async def delete_annotation_route(
    request: Request,
    annotation_id: str = Form(...),
    current_index: int = Form(default=0),
):
    """Soft-delete an annotation and return updated HTML."""
    from ace.models.annotation import delete_annotation

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
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

        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(content)


def _build_undo_response(
    request: Request, conn, coder_id: str, current_index: int, result: dict
) -> HTMLResponse:
    """Assemble the HTMX swap, status bar, optional navigate trigger, and flash hint.

    Used by both `/api/undo` and `/api/redo` after the manager has run the
    inverse mutation. `result` is the dict returned from
    `UndoManager.undo(conn)` / `redo(conn)`:
        {"description": str, "source_id": str | None, "flash_annotation_id": str | None}
    """
    from ace.models.assignment import get_assignments_for_coder

    description = result["description"]
    source_id = result["source_id"]
    flash_id = result["flash_annotation_id"]

    # Determine target_index: stay where the user is unless the op was
    # bound to a different source than the one currently visible.
    target_index = current_index
    headers: dict = {}

    if source_id is not None:
        assignments = get_assignments_for_coder(conn, coder_id)
        idx = next(
            (i for i, a in enumerate(assignments) if a["source_id"] == source_id),
            None,
        )
        if idx is None:
            description += " (source no longer assigned)"
        elif idx != current_index:
            target_index = idx
            headers["HX-Trigger"] = json.dumps(
                {"ace-navigate": {"index": target_index, "total": len(assignments)}}
            )

    content = _render_full_coding_oob(request, conn, coder_id, target_index)
    # _oob_status returns an HTMLResponse — extract its body to concat as a string.
    # It already emits an _oob_announce internally, so no separate announce call here.
    status_html = _oob_status(description, "ok").body.decode()
    content += status_html

    if flash_id is not None:
        # One-shot inline script that defers to bridge.js after settle. The
        # OOB swap replaces any previous flash hint on the page so multiple
        # consecutive undo/redo ops cleanly chain.
        content += (
            f'<script id="ace-undo-flash" hx-swap-oob="outerHTML">'
            f'window.addEventListener("htmx:afterSettle",function(e){{'
            f'if(window._flashAnnotation)window._flashAnnotation({json.dumps(flash_id)});'
            f'}},{{once:true}});</script>'
        )

    return HTMLResponse(content, headers=headers)


@router.post("/undo")
async def undo_route(
    request: Request,
    current_index: int = Form(default=0),
):
    """Pop the top entry from the global undo stack and replay its inverse."""
    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        mgr = _get_undo_manager(request)

        # OOB-only responses (no #text-panel content) — tell HTMX to skip the
        # primary swap; otherwise it would replace the text panel with empty.
        no_swap = {"HX-Reswap": "none"}

        if not mgr.can_undo():
            return _with_headers(_oob_status("Nothing to undo", "ok"), no_swap)

        try:
            result = mgr.undo(conn)
        except Exception:
            logger.exception("Undo failed")
            return _with_headers(_oob_status("Undo failed — please report this", "err"), no_swap)

        return _build_undo_response(request, conn, coder_id, current_index, result)


@router.post("/redo")
async def redo_route(
    request: Request,
    current_index: int = Form(default=0),
):
    """Pop the top entry from the global redo stack and replay it forward."""
    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        mgr = _get_undo_manager(request)

        no_swap = {"HX-Reswap": "none"}

        if not mgr.can_redo():
            return _with_headers(_oob_status("Nothing to redo", "ok"), no_swap)

        try:
            result = mgr.redo(conn)
        except Exception:
            logger.exception("Redo failed")
            return _with_headers(_oob_status("Redo failed — please report this", "err"), no_swap)

        return _build_undo_response(request, conn, coder_id, current_index, result)


# ---------------------------------------------------------------------------
# Source navigation + flag routes
# ---------------------------------------------------------------------------


@router.post("/code/navigate")
async def navigate_route(
    request: Request,
    current_index: int = Form(default=0),
    target_index: int = Form(default=0),
):
    """Navigate between sources."""
    from ace.models.assignment import get_assignments_for_coder

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        assignments = get_assignments_for_coder(conn, coder_id)
        if not assignments:
            return HTMLResponse("", status_code=400)

        total = len(assignments)

        # Clamp target
        if target_index < 0:
            target_index = 0
        if target_index >= total:
            target_index = total - 1

        content = _render_full_coding_oob(request, conn, coder_id, target_index)
        trigger = json.dumps({"ace-navigate": {"index": target_index, "total": total}})
        return HTMLResponse(content, headers={"HX-Trigger": trigger})


@router.post("/code/flag")
async def flag_route(
    request: Request,
    source_index: int = Form(default=0),
):
    """Toggle the flagged status of the current source."""
    from ace.models.assignment import get_assignments_for_coder, set_flagged

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        assignments = get_assignments_for_coder(conn, coder_id)
        if not assignments or source_index >= len(assignments):
            return HTMLResponse("", status_code=400)

        assignment = assignments[source_index]
        source_id = assignment["source_id"]
        prev_flagged = bool(assignment["flagged"])
        new_flagged = not prev_flagged
        set_flagged(conn, source_id, coder_id, new_flagged)
        _get_undo_manager(request).record_flag_toggle(source_id, coder_id, prev_flagged)

        msg = "Source flagged" if new_flagged else "Source unflagged"
        content = _render_full_coding_oob(request, conn, coder_id, source_index) + _oob_announce(msg)
        return HTMLResponse(content)


# ---------------------------------------------------------------------------
# Source note routes
# ---------------------------------------------------------------------------


@router.get("/source-note/{source_id}")
async def get_source_note(request: Request, source_id: str):
    """Return the current coder's note text for this source (empty if none)."""
    from ace.models.source_note import get_note

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        row = conn.execute("SELECT id FROM source WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            return JSONResponse({"error": "source not found"}, status_code=404)
        text = get_note(conn, source_id, coder_id) or ""
        return JSONResponse({"note_text": text})


@router.put("/source-note/{source_id}")
async def put_source_note(
    request: Request,
    source_id: str,
    note_text: str = Form(default=""),
):
    """Upsert (or delete via empty text) the current coder's note for a source.

    Returns a minimal JSON response (no HTMX swap) so the save doesn't
    interfere with the SVG highlight overlay or trigger idiomorph errors.
    The JS caller updates the pill state client-side.
    """
    from ace.models.assignment import get_assignments_for_coder
    from ace.models.source_note import upsert_note

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        assignments = get_assignments_for_coder(conn, coder_id)
        found = any(a["source_id"] == source_id for a in assignments)
        if not found:
            return JSONResponse({"ok": False}, status_code=404)

        upsert_note(conn, source_id, coder_id, note_text)

        return JSONResponse({"ok": True, "has_note": bool(note_text.strip()), "promoted": False})


@router.get("/export/notes")
async def export_notes_route(request: Request):
    """Export all source notes for the current coder as a CSV download."""
    from ace.services.notes_exporter import export_notes_csv

    coder_id = _require_coder(request)
    return _csv_download(
        request,
        "notes",
        lambda conn, path: export_notes_csv(conn, coder_id, path),
    )


@router.post("/code/apply-sentence")
async def annotate_sentence(
    request: Request,
    code_id: str = Form(...),
    sentence_index: int = Form(...),
    current_index: int = Form(default=0),
):
    """Apply a code to a sentence with auto-merge.

    If the same code already exists on this sentence, toggle it off.
    If an adjacent sentence already has the same code, expand that
    annotation to include this sentence (merge) instead of creating a new row.
    Otherwise, add a new annotation alongside any existing codes.
    """
    from ace.models.annotation import (
        add_annotation, delete_annotation, expand_annotation, get_annotations_for_source,
    )
    from ace.models.source import get_source_content
    from ace.services.text_splitter import split_into_units

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        source_id = _resolve_source_id(conn, coder_id, current_index)
        if source_id is None:
            return HTMLResponse("", status_code=400)

        content_row = get_source_content(conn, source_id)
        if not content_row:
            return HTMLResponse("", status_code=400)

        source_text = content_row["content_text"]
        units = split_into_units(source_text)
        if sentence_index < 0 or sentence_index >= len(units):
            return HTMLResponse("", status_code=400)

        unit = units[sentence_index]
        start = unit["start_offset"]
        end = unit["end_offset"]

        # Check if this exact code already exists on this sentence (toggle)
        existing = get_annotations_for_source(conn, source_id, coder_id)
        existing_same_code = None
        for ann in existing:
            if ann["start_offset"] < end and ann["end_offset"] > start:
                if ann["code_id"] == code_id:
                    existing_same_code = ann
                    break

        undo = _get_undo_manager(request)

        if existing_same_code:
            # Toggle off: remove this specific code
            delete_annotation(conn, existing_same_code["id"])
            undo.record_delete(source_id, existing_same_code["id"])
        else:
            # Auto-merge: check if adjacent sentence already has the same code
            neighbour = None
            for ann in existing:
                if ann["code_id"] != code_id:
                    continue
                # Adjacent = annotation ends where this sentence starts (within 5 chars gap)
                # or annotation starts where this sentence ends
                gap_before = start - ann["end_offset"]
                gap_after = ann["start_offset"] - end
                if 0 <= gap_before <= 5 or 0 <= gap_after <= 5:
                    neighbour = ann
                    break

            if neighbour:
                # Expand the existing annotation to include this sentence
                new_start = min(neighbour["start_offset"], start)
                new_end = max(neighbour["end_offset"], end)
                new_text = source_text[new_start:new_end]
                expand_annotation(conn, neighbour["id"], new_start, new_end, new_text)
                undo.record_add(source_id, neighbour["id"])
            else:
                ann_id = add_annotation(
                    conn, source_id, coder_id, code_id,
                    start, end, unit["text"],
                )
                undo.record_add(source_id, ann_id)

        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(content)


@router.post("/code/delete-sentence")
async def delete_sentence_annotations(
    request: Request,
    sentence_index: int = Form(...),
    current_index: int = Form(default=0),
):
    """Delete the most recently applied annotation on a focused sentence (X key).

    Press X multiple times to remove codes one by one (last-applied first).
    """
    from ace.models.annotation import delete_annotation
    from ace.models.source import get_source_content
    from ace.services.text_splitter import split_into_units

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        source_id = _resolve_source_id(conn, coder_id, current_index)
        if source_id is None:
            return HTMLResponse("", status_code=400)

        content_row = get_source_content(conn, source_id)
        if not content_row:
            return HTMLResponse("", status_code=400)

        units = split_into_units(content_row["content_text"])
        if sentence_index < 0 or sentence_index >= len(units):
            return HTMLResponse("", status_code=400)

        unit = units[sentence_index]
        start = unit["start_offset"]
        end = unit["end_offset"]

        # Find most recently created annotation overlapping this sentence
        most_recent = conn.execute(
            "SELECT id FROM annotation "
            "WHERE source_id = ? AND coder_id = ? AND deleted_at IS NULL "
            "AND start_offset < ? AND end_offset > ? "
            "ORDER BY created_at DESC LIMIT 1",
            (source_id, coder_id, end, start),
        ).fetchone()

        undo = _get_undo_manager(request)
        if most_recent:
            delete_annotation(conn, most_recent["id"])
            undo.record_delete(source_id, most_recent["id"])

        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        if most_recent:
            content += _oob_announce("Annotation removed")
        return HTMLResponse(content)


# ---------------------------------------------------------------------------
# Codebook CRUD helpers
# ---------------------------------------------------------------------------


def _render_code_sidebar(request: Request, conn, coder_id: str, current_index: int) -> str:
    """Render just the code sidebar block."""
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    project_path = request.app.state.project_path
    ctx = _coding_context(conn, coder_id, current_index, project_path=project_path)
    ctx["request"] = request
    return render_block(templates.env, "coding.html", "code_sidebar", ctx)


# ---------------------------------------------------------------------------
# Codebook CRUD routes
# ---------------------------------------------------------------------------


@router.post("/codes")
async def create_code(
    request: Request,
    name: str = Form(...),
    current_index: int = Form(default=0),
    group_name: str | None = Form(default=None),
):
    """Create a new code and return updated sidebar."""
    from ace.models.codebook import add_code, list_codes, next_colour

    coder_id = _require_coder(request)

    name = name.strip()
    if not name:
        return _oob_status("Code name cannot be empty.")

    with _project_db(request) as conn:
        existing = list_codes(conn)
        colour = next_colour(len(existing))
        gn = group_name.strip() if group_name else None
        try:
            new_code_id = add_code(conn, name, colour, group_name=gn or None)
        except Exception:
            return _oob_status(f"A code named '{name}' already exists.")
        _get_undo_manager(request).record_code_add(new_code_id)
        content = _render_code_sidebar(request, conn, coder_id, current_index)
        return HTMLResponse(content)


@router.post("/codes/reorder")
async def reorder_codes_route(
    request: Request,
    code_ids: str = Form(...),
    current_index: int = Form(default=0),
):
    """Reorder codes and return updated sidebar."""
    from ace.models.codebook import reorder_codes

    coder_id = _require_coder(request)

    try:
        ids_list = json.loads(code_ids)
    except (json.JSONDecodeError, TypeError):
        return _oob_status("Invalid code_ids format.")

    with _project_db(request) as conn:
        # ORDER BY id keeps prev/new aligned across the two reads so the undo
        # payload zips the right (id, sort_order) pairs — SQLite makes no
        # default ordering guarantee.
        prev = [
            (r["id"], r["sort_order"])
            for r in conn.execute(
                "SELECT id, sort_order FROM codebook_code WHERE deleted_at IS NULL ORDER BY id"
            ).fetchall()
        ]
        reorder_codes(conn, ids_list)
        new = [
            (r["id"], r["sort_order"])
            for r in conn.execute(
                "SELECT id, sort_order FROM codebook_code WHERE deleted_at IS NULL ORDER BY id"
            ).fetchall()
        ]
        # Skip recording when nothing actually changed. The client uses this
        # endpoint to re-render the sidebar after side-channel mutations
        # (group rename, etc.) and would otherwise pollute the undo stack
        # with no-op entries — making one user drag take two undo presses.
        if prev != new:
            _get_undo_manager(request).record_code_reorder(prev, new)
        content = _render_code_sidebar(request, conn, coder_id, current_index)
        return HTMLResponse(content)


# ---------------------------------------------------------------------------
# Codebook import / export  (registered before {code_id} to avoid path clash)
# ---------------------------------------------------------------------------


@router.get("/codes/export")
async def export_codebook(request: Request):
    """Export the codebook as a CSV file download."""
    from ace.models.codebook import export_codebook_to_csv

    with _project_db(request) as conn:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        tmp.close()
        export_codebook_to_csv(conn, tmp.name)

    return FileResponse(
        tmp.name,
        media_type="text/csv",
        filename="codebook.csv",
    )


@router.post("/codes/import/preview-path")
async def import_codebook_preview_path(
    request: Request,
    path: str = Form(...),
    current_index: int = Form(default=0),
):
    """Preview a codebook CSV from a local file path (native file picker flow)."""
    from ace.models.codebook import preview_codebook_csv

    coder_id = _require_coder(request)

    file_path = Path(path)
    if file_path.suffix.lower() != ".csv":
        return _oob_status("Please select a valid CSV file.")

    try:
        with _project_db(request) as conn:
            previewed = preview_codebook_csv(conn, str(file_path))
    except Exception as e:
        return _oob_status(f"Could not parse CSV: {e}")

    new_codes = [c for c in previewed if not c["exists"]]
    existing_codes = [c for c in previewed if c["exists"]]

    groups: dict = {}
    for code in previewed:
        gn = code.get("group_name") or ""
        groups.setdefault(gn, []).append(code)

    preview_parts = []
    for group_name, codes in groups.items():
        if group_name:
            preview_parts.append(
                f'<div class="ace-import-group-label">{html.escape(group_name)}</div>'
            )
        for code in codes:
            esc_name = html.escape(code["name"])
            if code["exists"]:
                preview_parts.append(
                    f'<div class="ace-import-row ace-import-row--exists">'
                    f'<span style="width:7px;height:7px;border-radius:50%;'
                    f'background:var(--ace-text-muted);display:inline-block"></span>'
                    f'{esc_name}'
                    f'<span class="ace-import-badge ace-import-badge--exists">exists</span>'
                    f'</div>'
                )
            else:
                esc_colour = html.escape(code["colour"])
                preview_parts.append(
                    f'<div class="ace-import-row ace-import-row--new">'
                    f'<span style="width:7px;height:7px;border-radius:50%;'
                    f'background:{esc_colour};display:inline-block"></span>'
                    f'{esc_name}'
                    f'<span class="ace-import-badge ace-import-badge--new">new</span>'
                    f'</div>'
                )
    preview_rows = "".join(preview_parts)

    filename = html.escape(file_path.name)
    new_count = len(new_codes)
    exist_count = len(existing_codes)
    subtitle_parts = [filename]
    if exist_count > 0:
        subtitle_parts.append(f"{exist_count} already exist (skipped)")

    codes_for_import = [
        {"name": c["name"], "colour": c["colour"], "group_name": c.get("group_name")}
        for c in new_codes
    ]
    codes_json_escaped = html.escape(json.dumps(codes_for_import))

    dialog_html = (
        f'<dialog class="ace-dialog ace-import-dialog">'
        f'<div class="ace-import-dialog-title">Import Codebook</div>'
        f'<div class="ace-import-dialog-sub">{" · ".join(subtitle_parts)}</div>'
    )

    if new_count > 0:
        dialog_html += (
            f'<div class="ace-import-preview">'
            f'<div class="ace-import-preview-header">Preview</div>'
            f'<div class="ace-import-preview-list">{preview_rows}</div>'
            f'</div>'
        )
    else:
        dialog_html += (
            '<div class="ace-import-empty">'
            'All codes in this file already exist in your codebook.</div>'
        )

    dialog_html += (
        '<div class="ace-import-actions">'
        '<button type="button" class="ace-btn" onclick="this.closest(\'dialog\').close()">Cancel</button>'
    )

    if new_count > 0:
        dialog_html += (
            f'<button type="button" class="ace-btn ace-btn--primary" '
            f'onclick="aceImportFromPreview(this)" '
            f'data-codes="{codes_json_escaped}" '
            f'data-current-index="{current_index}">'
            f'Import {new_count} code{"s" if new_count != 1 else ""}</button>'
        )

    dialog_html += '</div></dialog>'

    return HTMLResponse(dialog_html)


@router.post("/codes/import")
async def import_codebook(
    request: Request,
    codes_json: str = Form(...),
    current_index: int = Form(default=0),
):
    """Import selected codes from a previously previewed CSV."""
    from ace.models.codebook import import_selected_codes

    coder_id = _require_coder(request)

    try:
        codes_list = json.loads(codes_json)
    except (json.JSONDecodeError, TypeError):
        return _oob_status("Invalid codes_json format.")

    with _project_db(request) as conn:
        imported_ids = import_selected_codes(conn, codes_list)
        if imported_ids:
            _get_undo_manager(request).record_codebook_import(imported_ids)
        content = _render_code_sidebar(request, conn, coder_id, current_index)

    # Clean up temp file
    tmp_path = getattr(request.app.state, "codebook_import_tmp", None)
    if tmp_path:
        Path(tmp_path).unlink(missing_ok=True)
        request.app.state.codebook_import_tmp = None

    return HTMLResponse(content)


# ---------------------------------------------------------------------------
# Codebook {code_id} routes
# ---------------------------------------------------------------------------


@router.put("/codes/rename-group")
async def rename_group_route(
    request: Request,
    old_name: str = Form(...),
    new_name: str = Form(...),
    current_index: int = Form(default=0),
):
    """Rename a code group and return updated sidebar + text panel."""
    from ace.models.codebook import rename_group

    coder_id = _require_coder(request)

    new_name = new_name.strip()
    if not new_name:
        return _oob_status("Group name cannot be empty.")

    with _project_db(request) as conn:
        rename_group(conn, old_name, new_name)
        _get_undo_manager(request).record_group_rename(old_name, new_name)
        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(content)


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

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        kwargs: dict = {}
        if name is not None:
            name = name.strip()
            if not name:
                return _oob_status("Code name cannot be empty.")
            kwargs["name"] = name
        if colour is not None:
            if not re.fullmatch(r'#[0-9a-fA-F]{6}', colour):
                return _oob_status("Invalid colour format.")
            kwargs["colour"] = colour
        if group_name is not None:
            kwargs["group_name"] = group_name

        # Read the prior state so we can record the right inverse op(s).
        prev = conn.execute(
            "SELECT name, colour, group_name FROM codebook_code WHERE id = ?",
            (code_id,),
        ).fetchone()
        if prev is None:
            return _oob_status("Code not found.")

        try:
            update_code(conn, code_id, **kwargs)
        except Exception:
            return _oob_status("A code with that name already exists.")

        mgr = _get_undo_manager(request)
        if "name" in kwargs and kwargs["name"] != prev["name"]:
            mgr.record_code_rename(code_id, prev["name"], kwargs["name"])
        if "colour" in kwargs and kwargs["colour"] != prev["colour"]:
            mgr.record_code_recolour(code_id, prev["colour"], kwargs["colour"])
        if "group_name" in kwargs:
            new_group = kwargs["group_name"] if kwargs["group_name"] != "" else None
            if new_group != prev["group_name"]:
                mgr.record_code_change_group(code_id, prev["group_name"], new_group)

        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(content)


@router.delete("/codes/{code_id}")
async def delete_code_route(
    request: Request,
    code_id: str,
    current_index: int = Query(default=0),
):
    """Delete a code (cascades annotations) and return sidebar + text panel."""
    from ace.models.codebook import delete_code

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        # Capture the name before deletion — the row is gone afterwards.
        name_row = conn.execute(
            "SELECT name FROM codebook_code WHERE id = ?", (code_id,)
        ).fetchone()
        code_name = name_row["name"] if name_row else "(deleted code)"

        affected = delete_code(conn, code_id)
        _get_undo_manager(request).record_code_delete(code_id, affected)
        content = _render_full_coding_oob(request, conn, coder_id, current_index)

        # Soft-delete affordance: status bar carries an inline [Z] undo keycap.
        n = len(affected)
        if n > 0:
            unit = "annotation" if n == 1 else "annotations"
            message = f'Deleted "{code_name}" · {n} {unit} removed'
        else:
            message = f'Deleted "{code_name}"'
        content += _oob_status_undo(message)

        return HTMLResponse(content)


# ---------------------------------------------------------------------------
# Agreement routes
# ---------------------------------------------------------------------------


def _agreement_error(message: str) -> str:
    return (
        '<h1 class="ace-agreement-title">Inter-Coder Agreement</h1>'
        '<div class="ace-agreement-error">'
        f'<p>{html.escape(message)}</p>'
        '<button class="ace-agreement-choose-btn" onclick="acePickAndCompute()">Choose different files</button>'
        '</div>'
    )


def _agreement_fmt(val: float | None, decimals: int = 2, is_pct: bool = False) -> str:
    if val is None:
        return "\u2013"
    if is_pct:
        return f"{val * 100:.1f}"
    return f"{val:.{decimals}f}"


def _render_agreement_results(result, dataset, loader, jinja_env) -> str:
    from ace.services.agreement_verdict import classify_code, classify_overall

    n_coders = result.n_coders

    # Compute totals for context bar
    all_source_hashes = set()
    for fd in loader._file_data:
        all_source_hashes |= {s["content_hash"] for s in fd["sources"].values()}
    all_code_names = set()
    for fd in loader._file_data:
        all_code_names |= {info["name"] for info in fd["codes"].values()}

    # Build per-code verdicts
    code_verdicts = {
        name: classify_code(m) for name, m in result.per_code.items()
    }

    # Sort codes in codebook order (by sort_order from MatchedCode)
    code_order = {c.name: c for c in dataset.codes}
    per_code_sorted = sorted(
        result.per_code.items(),
        key=lambda item: code_order[item[0]].sort_order if item[0] in code_order else 0,
    )

    # Build group structure for template (with 1-based index)
    code_groups = []
    current_group = None
    code_idx = 1
    for name, metrics in per_code_sorted:
        mc = code_order.get(name)
        group = mc.group_name if mc else None
        if group != current_group:
            code_groups.append({"type": "group", "name": group})
            current_group = group
        code_groups.append({
            "type": "code",
            "name": name,
            "metrics": metrics,
            "verdict": code_verdicts[name],
            "index": code_idx,
        })
        code_idx += 1

    # Build code index for verdict text (1-based)
    code_index = {
        item["name"]: item["index"]
        for item in code_groups
        if item["type"] == "code"
    }

    # Overall verdict (needs code_index for large codebooks)
    verdict = classify_overall(result, code_verdicts, code_index)

    # Pairwise (3+ coders)
    pairwise_sorted = []
    if n_coders >= 3 and result.pairwise:
        coder_labels = {c.id: c.label for c in dataset.coders}
        for (cid_a, cid_b), pm in sorted(
            result.pairwise.items(),
            key=lambda x: x[1].gwets_ac1 if x[1].gwets_ac1 is not None else -1,
        ):
            label = (
                f"{coder_labels.get(cid_a, cid_a)} \u2194 "
                f"{coder_labels.get(cid_b, cid_b)}"
            )
            pairwise_sorted.append((label, pm, classify_code(pm, pairwise=True)))

    # Table numbering
    table_per_code = 1
    table_pairwise = 2 if pairwise_sorted else None
    table_full = 3 if pairwise_sorted else 2

    # Overall verdict for overall row
    overall_verdict = classify_code(result.overall)

    tmpl = jinja_env.get_template("agreement_results.html")
    return tmpl.render(
        n_coders=n_coders,
        n_sources=result.n_sources,
        n_codes=result.n_codes,
        total_sources=len(all_source_hashes),
        total_codes=len(all_code_names),
        warnings=dataset.warnings,
        verdict=verdict,
        code_groups=code_groups,
        code_verdicts=code_verdicts,
        per_code_sorted=per_code_sorted,
        overall=result.overall,
        overall_verdict=overall_verdict,
        pairwise_sorted=pairwise_sorted,
        kappa_header="Cohen \u03ba" if n_coders == 2 else "Fleiss \u03ba",
        fmt=_agreement_fmt,
        table_per_code=table_per_code,
        table_pairwise=table_pairwise,
        table_full=table_full,
    )


@router.post("/agreement/compute")
async def agreement_compute(
    request: Request,
    paths: str = Form(...),
):
    """Load files, compute agreement, return minimalist results HTML."""
    from ace.services.agreement_loader import AgreementLoader
    from ace.services.agreement_computer import compute_agreement

    try:
        path_list = json.loads(paths)
    except (json.JSONDecodeError, TypeError):
        return HTMLResponse(_agreement_error("Invalid file paths."), status_code=400)

    if not isinstance(path_list, list) or not all(isinstance(p, str) and p for p in path_list):
        return HTMLResponse(_agreement_error("Invalid file paths."), status_code=400)

    if len(path_list) < 2:
        return HTMLResponse(_agreement_error("Select at least 2 .ace files."), status_code=400)

    loader = AgreementLoader()
    for p in path_list:
        result = loader.add_file(p)
        if result.get("error"):
            return HTMLResponse(
                _agreement_error(f"Error loading {Path(p).name}: {result['error']}"),
                status_code=400,
            )

    # Store loader for export endpoints
    request.app.state.agreement_loader = loader

    try:
        dataset = loader.build_dataset()
    except Exception:
        return HTMLResponse(_agreement_error("Cannot compute agreement. Check that the files have shared sources and codes."), status_code=400)

    if not dataset.sources:
        return HTMLResponse(
            _agreement_error("No shared sources found across the selected files."),
            status_code=400,
        )

    result = compute_agreement(dataset)

    request.app.state.agreement_dataset = dataset
    request.app.state.agreement_result = result

    html_out = _render_agreement_results(result, dataset, loader, request.app.state.templates.env)
    return HTMLResponse(html_out)


@router.get("/agreement/export/results")
async def agreement_export_results(request: Request):
    """Export per-code metrics as CSV download."""
    import csv
    import io
    from datetime import date

    loader = getattr(request.app.state, "agreement_loader", None)
    dataset = getattr(request.app.state, "agreement_dataset", None)
    result = getattr(request.app.state, "agreement_result", None)
    if loader is None or loader.file_count < 2 or dataset is None or result is None:
        return HTMLResponse("No agreement data available. Compute first.", status_code=400)

    output = io.StringIO()

    # Metadata comment header
    file_names = ", ".join(f["filename"] for f in loader._files)
    coder_labels = ", ".join(c.label for c in dataset.coders)
    output.write(f"# ACE agreement summary — {date.today().isoformat()}\n")
    output.write(f"# Files: {file_names}\n")
    output.write(f"# Coders: {coder_labels}\n")
    output.write(f"# Sources: {result.n_sources}, Codes: {result.n_codes}\n")

    writer = csv.writer(output)
    writer.writerow([
        "code", "percent_agreement",
        "krippendorffs_alpha", "cohens_kappa", "fleiss_kappa",
        "congers_kappa", "gwets_ac1", "brennan_prediger",
        "n_sources", "n_positions",
    ])

    def _fmt(v):
        return f"{v:.4f}" if v is not None else ""

    for code_name in sorted(result.per_code):
        m = result.per_code[code_name]
        writer.writerow([
            code_name,
            _fmt(m.percent_agreement),
            _fmt(m.krippendorffs_alpha),
            _fmt(m.cohens_kappa),
            _fmt(m.fleiss_kappa),
            _fmt(m.congers_kappa),
            _fmt(m.gwets_ac1),
            _fmt(m.brennan_prediger),
            m.n_sources,
            m.n_positions,
        ])

    # Overall row
    o = result.overall
    writer.writerow([
        "Overall",
        _fmt(o.percent_agreement),
        _fmt(o.krippendorffs_alpha),
        _fmt(o.cohens_kappa),
        _fmt(o.fleiss_kappa),
        _fmt(o.congers_kappa),
        _fmt(o.gwets_ac1),
        _fmt(o.brennan_prediger),
        result.n_sources,
        o.n_positions,
    ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="agreement_summary.csv"'},
    )


@router.get("/agreement/export/raw")
async def agreement_export_raw(request: Request):
    """Export raw annotation data as long-form CSV for reproducibility in R/Python."""
    import csv
    import io
    from datetime import date

    loader = getattr(request.app.state, "agreement_loader", None)
    dataset = getattr(request.app.state, "agreement_dataset", None)
    if loader is None or loader.file_count < 2 or dataset is None:
        return HTMLResponse("No agreement data available. Compute first.", status_code=400)

    output = io.StringIO()
    coder_labels = ", ".join(c.label for c in dataset.coders)
    output.write(f"# ACE raw agreement data — {date.today().isoformat()}\n")
    output.write(f"# Coders: {coder_labels}\n")
    output.write(f"# Sources: {len(dataset.sources)}, Codes: {len(dataset.codes)}\n")

    writer = csv.writer(output)
    writer.writerow(["source_id", "start_offset", "end_offset", "coder_id", "code_name"])

    source_lookup = {s.content_hash: s.display_id for s in dataset.sources}

    for ann in sorted(dataset.annotations, key=lambda a: (a.source_hash, a.start_offset, a.coder_id)):
        source_id = source_lookup.get(ann.source_hash, ann.source_hash)
        writer.writerow([source_id, ann.start_offset, ann.end_offset, ann.coder_id, ann.code_name])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="agreement_raw_data.csv"'},
    )


@router.get("/agreement/export/references")
async def agreement_export_references():
    """Download the BibTeX references file for agreement metrics."""
    bib_path = Path(__file__).resolve().parent.parent / "static" / "agreement_references.bib"
    content = bib_path.read_text(encoding="utf-8")
    return Response(
        content=content,
        media_type="application/x-bibtex",
        headers={"Content-Disposition": 'attachment; filename="references.bib"'},
    )


@router.get("/agreement/export/methodology")
async def agreement_export_methodology():
    """Download the methodology markdown file describing agreement computations."""
    md_path = Path(__file__).resolve().parent.parent / "static" / "agreement_methodology.md"
    content = md_path.read_text(encoding="utf-8")
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="methodology.md"'},
    )
