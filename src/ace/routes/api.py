"""API routes — JSON/HTMX fragment responses."""

from __future__ import annotations

import asyncio
import platform
import subprocess

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

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
