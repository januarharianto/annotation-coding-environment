"""Playwright fixtures for the codebook redesign e2e suite.

Each test gets its OWN fresh project + uvicorn process so that mutating
gestures (cut/paste, wrap-into-folder, drag) do not bleed across tests.
Spinning up uvicorn is ~1.5–2 s per test; with ~10 tests across three
browsers that is ~45–60 s, which we accept in exchange for isolation.

Browser availability is sniffed from the playwright cache directory so
that we skip parametrize values for engines that aren't installed instead
of failing them.
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

# Skip the entire e2e folder if playwright isn't importable.
pytest.importorskip("playwright")


# ---------------------------------------------------------------------------
# Browser availability detection (parametrize helper)
# ---------------------------------------------------------------------------


def _playwright_cache_dir() -> Path:
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env:
        return Path(env)
    sysname = platform.system()
    if sysname == "Darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    if sysname == "Linux":
        return Path.home() / ".cache" / "ms-playwright"
    if sysname == "Windows":
        local_appdata = os.environ.get(
            "LOCALAPPDATA", str(Path.home() / "AppData" / "Local")
        )
        return Path(local_appdata) / "ms-playwright"
    raise RuntimeError(f"Unsupported platform: {sysname}")


def _installed_browsers() -> list[str]:
    """Return the subset of ['chromium', 'firefox', 'webkit'] available locally."""
    cache = _playwright_cache_dir()
    if not cache.exists():
        return ["chromium"]  # fall back; let playwright complain at launch time
    names = [p.name for p in cache.iterdir() if p.is_dir()]
    out = []
    for engine in ("chromium", "firefox", "webkit"):
        if any(n.startswith(f"{engine}-") for n in names):
            out.append(engine)
    return out or ["chromium"]


BROWSERS = _installed_browsers()


def browser_params():
    """Return a parametrize argvalues list with skip markers for missing engines."""
    out = []
    for engine in ("chromium", "firefox", "webkit"):
        if engine in BROWSERS:
            out.append(engine)
        else:
            out.append(
                pytest.param(
                    engine,
                    marks=pytest.mark.skip(reason=f"playwright {engine} not installed"),
                )
            )
    return out


# ---------------------------------------------------------------------------
# Server fixture
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.5).read()
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(0.1)
    raise RuntimeError(f"server did not start at {url}: {last_exc!r}")


@pytest.fixture()
def ace_server(tmp_path):
    """Spawn uvicorn on a free port with a fresh project. Yields the base URL.

    Function-scoped on purpose: tests in this folder mutate codebook state
    (create folders, cut/paste, drag). Sharing the project across tests
    would couple them in ways that make ordering-sensitive failures hard
    to diagnose.
    """
    from ace.db.connection import create_project, open_project
    from ace.models.codebook import add_code
    from ace.models.source import add_source
    from ace.models.assignment import add_assignment
    from ace.models.project import list_coders

    project = tmp_path / "test.ace"
    create_project(str(project), "E2E Test")
    conn = open_project(str(project))
    try:
        # Three Okabe-Ito-friendly codes — enough rows for keyboard +
        # cut/paste + drag tests without crowding the sidebar.
        add_code(conn, "Alpha", "#D55E00")
        add_code(conn, "Bravo", "#56B4E9")
        add_code(conn, "Charlie", "#009E73")
        # One source so /code renders a non-empty text panel — required for
        # clicking #text-panel to work as a "switch active zone" gesture.
        sid = add_source(conn, "S001", "First sentence. Second sentence.", "row")
        coder = list_coders(conn)[0]["id"]
        add_assignment(conn, sid, coder)
    finally:
        conn.close()

    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "ace.app:create_app", "--factory",
            "--host", "127.0.0.1", "--port", str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(f"{base}/", timeout=10.0)
        # Open the project so /code can render against it.
        data = urllib.parse.urlencode({"path": str(project)}).encode()
        urllib.request.urlopen(f"{base}/api/project/open", data=data).read()
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
