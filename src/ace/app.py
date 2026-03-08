import os
import signal
import subprocess
import time
from pathlib import Path

# Store NiceGUI data in user config directory (not CWD)
_DATA_DIR = Path.home() / ".ace"
_DATA_DIR.mkdir(exist_ok=True)
os.environ.setdefault("NICEGUI_STORAGE_PATH", str(_DATA_DIR))

from nicegui import app, ui

from ace.pages import coding, import_page, landing

# Serve static assets (JS/CSS) and load global theme
static_dir = Path(__file__).parent / "static"
app.add_static_files("/static", str(static_dir))


@app.on_connect
def _inject_theme():
    ui.add_head_html('<link rel="stylesheet" href="/static/css/theme.css">')


# Register all page routes at import time (required by NiceGUI multiprocessing)
landing.register()
import_page.register()
coding.register()


def _kill_stale_server(port: int) -> None:
    """Kill any existing process on the given port so we can bind cleanly."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
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


def run():
    _kill_stale_server(8080)
    ui.run(host="127.0.0.1", port=8080, title="ACE", storage_secret="ace-local", reload=False)
