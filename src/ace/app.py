from pathlib import Path

from nicegui import app, ui

from ace.pages import coder, landing, manager

# Serve static assets (JS/CSS) and load global theme
static_dir = Path(__file__).parent / "static"
app.add_static_files("/static", str(static_dir))


@app.on_connect
def _inject_theme():
    ui.add_head_html('<link rel="stylesheet" href="/static/css/theme.css">')

# Register all page routes at import time (required by NiceGUI multiprocessing)
landing.register()
manager.register()
coder.register()


def run():
    ui.run(host="127.0.0.1", port=8080, title="ACE", storage_secret="ace-local", reload=False)
