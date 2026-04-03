# ACE — Annotation Coding Environment

A qualitative text coding tool for small research teams.

- Import references from CSV, Excel, or plain text files
- Create codes and subcodes
- Highlight passages with overlapping annotations and assign multiple codes to the same passage
- Merge results from multiple coders
- Compute inter-coder agreement using Krippendorff's alpha, Cohen's kappa, and others

## Install

Download the latest build from the [Releases page](https://github.com/januarharianto/annotation-coding-environment/releases). Open the `.dmg` (macOS) or run the `.exe` installer (Windows). Intel-based Macs are not supported.

The app is not code-signed yet, so your OS will complain on first launch:
- **macOS:** Right-click the app, select **Open**, then click **Open** again.
- **Windows:** Click **More info**, then **Run anyway**.

## Development

```
git clone https://github.com/januarharianto/annotation-coding-environment.git
cd annotation-coding-environment
uv run ace
```

Tests: `uv run pytest`

Needs [uv](https://docs.astral.sh/uv/getting-started/installation/).

### Desktop shell

The desktop app wraps the Python server in a [Tauri](https://tauri.app/) window. You need Rust and the Tauri CLI.

```
# Terminal 1 — Python server with hot reload
uv run uvicorn ace.app:create_app --factory --host 127.0.0.1 --port 18080 --reload --reload-dir src/ace

# Terminal 2 — Tauri dev shell
cd desktop && cargo tauri dev
```
