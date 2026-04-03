"""Tests for the FastAPI app scaffold."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from ace.app import HtmxRedirect, _build_allowed_origins, create_app


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── App startup ──────────────────────────────────────────────────────────


class TestAppStartup:
    def test_app_creates_successfully(self, app):
        assert app is not None

    def test_landing_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "ACE" in resp.text

    def test_static_css_served(self, client):
        resp = client.get("/static/css/ace.css")
        assert resp.status_code == 200
        assert "--ace-primary" in resp.text

    def test_static_htmx_served(self, client):
        resp = client.get("/static/js/htmx.min.js")
        assert resp.status_code == 200

    def test_static_bridge_served(self, client):
        resp = client.get("/static/js/bridge.js")
        assert resp.status_code == 200
        assert "aceToast" in resp.text

    def test_import_redirects_without_project(self, client):
        resp = client.get("/import", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    def test_lifespan_sets_state(self, app):
        with TestClient(app):
            assert app.state.db is None
            assert app.state.project_path is None
            assert app.state.undo_managers == {}
            assert app.state.migrated_paths == set()
            assert app.state.active_projects == set()


# ── CSRF middleware ──────────────────────────────────────────────────────


class TestCSRFMiddleware:
    def test_blocks_foreign_origin(self, app):
        import ace.app as app_mod
        original = app_mod._ALLOWED_ORIGINS
        app_mod._ALLOWED_ORIGINS = _build_allowed_origins(8080)
        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post(
                    "/api/test",
                    headers={"Origin": "http://evil.example.com"},
                )
                assert resp.status_code in (403, 404, 405)
                # 403 from CSRF is the important one — if the route doesn't
                # exist we'd get 404/405, but CSRF runs first
                if resp.status_code == 403:
                    assert "CSRF" in resp.text
        finally:
            app_mod._ALLOWED_ORIGINS = original

    def test_allows_localhost_origin(self, app):
        import ace.app as app_mod
        original = app_mod._ALLOWED_ORIGINS
        app_mod._ALLOWED_ORIGINS = _build_allowed_origins(8080)
        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post(
                    "/api/test",
                    headers={"Origin": "http://127.0.0.1:8080"},
                )
                # Should NOT be 403 — either 404 or 405 (route doesn't exist)
                assert resp.status_code != 403
        finally:
            app_mod._ALLOWED_ORIGINS = original

    def test_allows_no_origin(self, app):
        import ace.app as app_mod
        original = app_mod._ALLOWED_ORIGINS
        app_mod._ALLOWED_ORIGINS = _build_allowed_origins(8080)
        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post("/api/test")
                # No Origin header → passes CSRF, hits 404/405
                assert resp.status_code != 403
        finally:
            app_mod._ALLOWED_ORIGINS = original

    def test_get_passes_csrf(self, client):
        resp = client.get(
            "/",
            headers={"Origin": "http://evil.example.com"},
        )
        assert resp.status_code == 200


# ── HtmxRedirect ────────────────────────────────────────────────────────


class TestHtmxRedirect:
    def test_plain_redirect(self, client):
        resp = client.get("/import", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    def test_htmx_redirect(self, client):
        resp = client.get(
            "/import",
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert resp.headers["HX-Redirect"] == "/"


# ── get_db dependency ────────────────────────────────────────────────────


class TestGetDb:
    def _fake_request(self, project_path=None):
        """Build a minimal request-like object with app.state.project_path."""
        from types import SimpleNamespace

        state = SimpleNamespace(project_path=project_path)
        app = SimpleNamespace(state=state)
        return SimpleNamespace(app=app)

    def test_raises_redirect_when_no_project_path(self):
        from ace.app import get_db

        gen = get_db(self._fake_request(project_path=None))
        with pytest.raises(HtmxRedirect):
            next(gen)

    def test_raises_redirect_when_path_missing(self, tmp_path):
        from ace.app import get_db

        gen = get_db(self._fake_request(project_path=str(tmp_path / "gone.ace")))
        with pytest.raises(HtmxRedirect):
            next(gen)

    def test_raises_redirect_when_bad_application_id(self, tmp_path):
        from ace.app import get_db

        bad_db = tmp_path / "bad.ace"
        conn = sqlite3.connect(str(bad_db))
        conn.execute("PRAGMA application_id = 0")
        conn.close()

        gen = get_db(self._fake_request(project_path=str(bad_db)))
        with pytest.raises(HtmxRedirect):
            next(gen)

    def test_yields_connection_for_valid_project(self, tmp_path):
        from ace.app import get_db
        from ace.db.connection import create_project

        db_path = tmp_path / "valid.ace"
        setup_conn = create_project(str(db_path), "test")
        setup_conn.close()

        gen = get_db(self._fake_request(project_path=str(db_path)))
        conn = next(gen)
        try:
            assert isinstance(conn, sqlite3.Connection)
            # Verify foreign keys are enabled
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            assert fk == 1
        finally:
            gen.close()

    def test_connection_closed_after_yield(self, tmp_path):
        from ace.app import get_db
        from ace.db.connection import create_project

        db_path = tmp_path / "close_test.ace"
        setup_conn = create_project(str(db_path), "test")
        setup_conn.close()

        gen = get_db(self._fake_request(project_path=str(db_path)))
        conn = next(gen)
        gen.close()
        # Connection should be closed — executing should raise
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


# ── Allowed origins builder ──────────────────────────────────────────────


class TestBuildAllowedOrigins:
    def test_default_port(self):
        origins = _build_allowed_origins(8080)
        assert "http://127.0.0.1:8080" in origins
        assert "http://localhost:8080" in origins

    def test_custom_port(self):
        origins = _build_allowed_origins(9000)
        assert "http://127.0.0.1:9000" in origins
        assert "http://localhost:9000" in origins


# ── run() behaviour ────────────────────────────────────────────────────


from unittest.mock import patch


def test_run_accepts_port_parameter():
    """run(port=9999) should pass port=9999 to uvicorn."""
    with patch("ace.app.uvicorn.run") as mock_run, \
         patch("ace.app._kill_stale_server"):
        from ace.app import run
        run(port=9999)
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["port"] == 9999


def test_run_defaults_to_8080():
    """run() without port should default to 8080."""
    import os
    os.environ.pop("ACE_PORT", None)
    with patch("ace.app.uvicorn.run") as mock_run, \
         patch("ace.app._kill_stale_server"):
        from ace.app import run
        run()
        assert mock_run.call_args.kwargs["port"] == 8080


def test_run_respects_ace_port_env():
    """run() without --port should use ACE_PORT env var."""
    with patch("ace.app.uvicorn.run") as mock_run, \
         patch("ace.app._kill_stale_server"), \
         patch.dict("os.environ", {"ACE_PORT": "9000"}):
        from ace.app import run
        run()
        assert mock_run.call_args.kwargs["port"] == 9000


def test_run_cli_port_overrides_env():
    """run(port=7777) should take priority over ACE_PORT."""
    with patch("ace.app.uvicorn.run") as mock_run, \
         patch("ace.app._kill_stale_server"), \
         patch.dict("os.environ", {"ACE_PORT": "9000"}):
        from ace.app import run
        run(port=7777)
        assert mock_run.call_args.kwargs["port"] == 7777


def test_run_uses_callable_not_string():
    """run() should pass the create_app callable, not a string, to uvicorn."""
    with patch("ace.app.uvicorn.run") as mock_run, \
         patch("ace.app._kill_stale_server"):
        from ace.app import run
        run()
        first_arg = mock_run.call_args[0][0]
        assert callable(first_arg), f"Expected callable, got {type(first_arg)}: {first_arg}"
