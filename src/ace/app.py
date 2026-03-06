from pathlib import Path

from nicegui import app, ui

from ace.pages import landing
from ace.pages import manager
from ace.pages import coder


def run():
    # Serve static assets (JS/CSS)
    static_dir = Path(__file__).parent / "static"
    app.add_static_files("/static", str(static_dir))

    landing.register()
    manager.register()
    coder.register()

    ui.run(host="127.0.0.1", port=8080, title="ACE", storage_secret="ace-local")
