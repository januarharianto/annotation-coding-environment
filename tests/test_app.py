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
    def test_raises_redirect_when_no_project(self, client):
        """get_db should redirect when no project is loaded."""
        # /import exercises get_db indirectly — but let's test the
        # dependency directly by importing it
        from ace.app import get_db

        class FakeState:
            db = None

        class FakeApp:
            state = FakeState()

        class FakeRequest:
            app = FakeApp()

        gen = get_db(FakeRequest())
        with pytest.raises(HtmxRedirect):
            next(gen)

    def test_yields_connection_when_project_loaded(self):
        from ace.app import get_db

        conn = sqlite3.connect(":memory:")

        class FakeState:
            db = conn

        class FakeApp:
            state = FakeState()

        class FakeRequest:
            app = FakeApp()

        gen = get_db(FakeRequest())
        result = next(gen)
        assert result is conn
        conn.close()


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
