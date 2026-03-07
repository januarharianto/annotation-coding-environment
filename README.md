# ACE — Annotation Coding Environment

ACE is a desktop tool for qualitative text coding. You highlight text, assign codes, and ACE keeps track of everything in a single `.ace` file. It runs in your browser but works entirely offline — nothing is sent to the internet.

Built for research teams who need to code text data and measure agreement between coders.

## Install

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) (a Python package runner). Install it with:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows, use PowerShell:

```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then run ACE:

```
uvx ace-coder
```

This downloads ACE and opens it in your browser. You only need to do the uv install once.

## How it works

### 1. Create a project

Open ACE and click **New Project**. Choose a name and where to save the `.ace` file. This file holds everything — your texts, codes, and annotations.

### 2. Import your data

Bring in the text you want to code. ACE accepts:

- **CSV files** — pick which column has the text and which has participant IDs
- **Excel files** (`.xlsx`, `.xls`) — same as CSV
- **A folder of `.txt` files** — each file becomes one source

### 3. Start coding

The coding screen has two panels:

- **Left panel** — your list of codes. Type a name in the text field and press Enter to create one. Each code gets a colour automatically.
- **Right panel** — the text to annotate. Select text with your mouse, then click a code to apply it. The text highlights in that code's colour.

You can apply multiple codes to the same piece of text. Codes overlap and layer on top of each other.

### 4. Navigate sources

Use **Prev** and **Next** at the bottom to move between texts. Click **Mark Complete** when you've finished coding a source, or **Flag** it if you want to come back to it later.

The progress bar shows how many sources you've completed.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| **1–9** | Apply code 1–9 to selected text |
| **Ctrl+Z** (Cmd+Z on Mac) | Undo |
| **Ctrl+Shift+Z** (Cmd+Shift+Z) | Redo |
| **Ctrl+Enter** (Cmd+Enter) | Mark source complete |
| **Alt+Left/Right** | Previous/next source |
| **Escape** | Clear selection |

## Working with a team

ACE supports multiple coders working on the same dataset independently.

### Setting up

1. Create a project and import your data
2. Use the assignment tools to split sources across coders, with a configurable overlap percentage for reliability measurement
3. Export a coder package (`.ace` file) for each person

### Coding

Each coder opens their package in ACE and codes independently. They only see the sources assigned to them.

### Merging results

Import each coder's completed package back into the main project. ACE merges the annotations and calculates inter-coder reliability (Cohen's Kappa and percent agreement) on the overlapping sources.

## The .ace file

The `.ace` file is a SQLite database. You can open it with any SQLite tool if you want to inspect the data directly. ACE also exports annotations to CSV for analysis in R, Python, or Excel.

Keep your `.ace` files on a local drive, not in a cloud-sync folder (Dropbox, OneDrive, etc.). SQLite doesn't sync well with these services and you may lose data.

## Managing codes

- **Create** — type a name in the "New code..." field and press Enter
- **Rename** — click the menu button next to a code
- **Change colour** — click the menu button and pick from the palette (10 colourblind-accessible colours)
- **Delete** — click the menu button and confirm. Existing annotations keep their text but show as "Unknown"

## Notes

Each source has a notes field at the bottom of the right panel. Use it to record observations or flag things for later. Notes save automatically.

## Development

ACE is a Python app built with [NiceGUI](https://nicegui.io/). To work on it locally:

```
git clone https://github.com/januarharianto/annotation-coding-environment.git
cd annotation-coding-environment
uv run ace
```

Run the tests:

```
uv run pytest
```
