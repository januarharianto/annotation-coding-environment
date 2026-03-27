"""Tests for native OS file picker endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ace.routes.api import router

# Build a minimal FastAPI app around the router for testing.
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _mock_result(returncode: int = 0, stdout: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    return result


@patch("ace.routes.api.platform")
@patch("ace.routes.api._run_osascript")
def test_pick_file_returns_path(mock_osascript, mock_platform):
    mock_platform.system.return_value = "Darwin"
    mock_osascript.return_value = _mock_result(0, "/tmp/test.ace\n")

    response = client.post("/api/native/pick-file", data={"accept": ".ace"})

    assert response.status_code == 200
    assert response.json() == {"path": "/tmp/test.ace"}
    mock_osascript.assert_called_once()
    # Verify the osascript includes the type filter.
    script_arg = mock_osascript.call_args[0][0]
    assert 'of type {"ace"}' in script_arg


@patch("ace.routes.api.platform")
@patch("ace.routes.api._run_osascript")
def test_pick_file_returns_empty_on_cancel(mock_osascript, mock_platform):
    mock_platform.system.return_value = "Darwin"
    mock_osascript.return_value = _mock_result(1, "")

    response = client.post("/api/native/pick-file")

    assert response.status_code == 200
    assert response.json() == {"path": ""}


@patch("ace.routes.api.platform")
@patch("ace.routes.api._run_osascript")
def test_pick_folder_returns_path(mock_osascript, mock_platform):
    mock_platform.system.return_value = "Darwin"
    mock_osascript.return_value = _mock_result(0, "/tmp/my_folder/\n")

    response = client.post("/api/native/pick-folder")

    assert response.status_code == 200
    assert response.json() == {"path": "/tmp/my_folder/"}
    mock_osascript.assert_called_once()


@patch("ace.routes.api.platform")
@patch("ace.routes.api._run_osascript")
def test_pick_files_returns_multiple_paths(mock_osascript, mock_platform):
    mock_platform.system.return_value = "Darwin"
    mock_osascript.return_value = _mock_result(
        0, "/tmp/a.csv\n/tmp/b.xlsx\n"
    )

    response = client.post(
        "/api/native/pick-files", data={"accept": ".csv,.xlsx"}
    )

    assert response.status_code == 200
    assert response.json() == {"paths": ["/tmp/a.csv", "/tmp/b.xlsx"]}
    script_arg = mock_osascript.call_args[0][0]
    assert 'of type {"csv", "xlsx"}' in script_arg


@patch("ace.routes.api.platform")
def test_non_darwin_returns_empty(mock_platform):
    """Endpoints return empty values on non-macOS platforms."""
    mock_platform.system.return_value = "Linux"

    r1 = client.post("/api/native/pick-file")
    r2 = client.post("/api/native/pick-folder")
    r3 = client.post("/api/native/pick-files")

    assert r1.json() == {"path": ""}
    assert r2.json() == {"path": ""}
    assert r3.json() == {"paths": []}
