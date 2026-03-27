"""API routes — JSON/HTMX fragment responses."""

from __future__ import annotations

import asyncio
import platform
import sqlite3
import subprocess
from pathlib import Path

from fastapi import APIRouter, Form, Request
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
