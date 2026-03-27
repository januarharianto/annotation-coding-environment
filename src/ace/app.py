"""FastAPI application factory for ACE."""

import os
import secrets
import signal
import sqlite3
import subprocess
import time
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2_fragments.fastapi import Jinja2Blocks
from starlette.middleware.sessions import SessionMiddleware

from ace.db.connection import checkpoint_and_close, open_project
from ace.db.schema import ACE_APPLICATION_ID

_DATA_DIR = Path.home() / ".ace"
_PKG_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# HtmxRedirect — raised inside get_db or routes to redirect via HTMX
# ---------------------------------------------------------------------------


class HtmxRedirect(Exception):
    """Raise to redirect the client (works for both HTMX and plain requests)."""

    def __init__(self, url: str) -> None:
        self.url = url


def _htmx_redirect_handler(request: Request, exc: HtmxRedirect) -> Response:
    """Return an HX-Redirect header for HTMX requests, else a 302."""
    if request.headers.get("HX-Request"):
        return Response(
            status_code=200,
            headers={"HX-Redirect": exc.url},
        )
    return Response(
        status_code=302,
        headers={"Location": exc.url},
    )


# ---------------------------------------------------------------------------
# CSRF middleware
# ---------------------------------------------------------------------------

_ALLOWED_ORIGINS = frozenset()


def _build_allowed_origins(port: int) -> frozenset[str]:
    return frozenset(
        f"{scheme}://{host}:{port}"
        for scheme in ("http",)
        for host in ("127.0.0.1", "localhost")
    )


class _CSRFMiddleware:
    """Reject mutating requests whose Origin header doesn't match localhost."""

    _SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS", "TRACE"))

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if request.method not in self._SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin not in _ALLOWED_ORIGINS:
                response = Response("CSRF origin rejected", status_code=403)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# get_db dependency
# ---------------------------------------------------------------------------


def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    """Yield an open SQLite connection for the current project.

    Raises HtmxRedirect("/") if no project is loaded or the file is invalid.
    """
    conn: sqlite3.Connection | None = getattr(request.app.state, "db", None)
    if conn is None:
        raise HtmxRedirect("/")
    yield conn


DbDep = Annotated[sqlite3.Connection, Depends(get_db)]


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    _DATA_DIR.mkdir(exist_ok=True)
    app.state.db = None
    app.state.project_path = None
    yield
    conn: sqlite3.Connection | None = getattr(app.state, "db", None)
    if conn is not None:
        checkpoint_and_close(conn)
        app.state.db = None


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(lifespan=_lifespan)

    # Exception handlers
    app.add_exception_handler(HtmxRedirect, _htmx_redirect_handler)

    # Middleware (applied bottom-up: CSRF runs first, then session)
    app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))
    app.add_middleware(_CSRFMiddleware)

    # Static files
    app.mount("/static", StaticFiles(directory=str(_PKG_DIR / "static")), name="static")

    # Templates
    app.state.templates = Jinja2Blocks(directory=str(_PKG_DIR / "templates"))

    # Routes
    from ace.routes.api import router as api_router
    from ace.routes.pages import router as pages_router

    app.include_router(pages_router)
    app.include_router(api_router)

    return app


# ---------------------------------------------------------------------------
# Server management
# ---------------------------------------------------------------------------


def _kill_stale_server(port: int) -> None:
    """Kill any existing process on the given port so we can bind cleanly."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = result.stdout.strip().splitlines()
        if not pids:
            return
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
        time.sleep(0.5)
    except (subprocess.SubprocessError, FileNotFoundError):
        pass


def run() -> None:
    port = int(os.environ.get("ACE_PORT", "8080"))
    global _ALLOWED_ORIGINS
    _ALLOWED_ORIGINS = _build_allowed_origins(port)
    _kill_stale_server(port)
    uvicorn.run(
        "ace.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=port,
        log_level="info",
    )
