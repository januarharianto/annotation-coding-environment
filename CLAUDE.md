# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Structure
- `src/ace/` — main package (FastAPI + HTMX web app)
- `src/ace/app.py` — FastAPI app factory, middleware (CSRF, session), lifespan, `get_db` dependency, `run()`
- `src/ace/routes/pages.py` — GET routes for `/`, `/import`, `/code`, `/agreement`
- `src/ace/routes/api.py` — HTMX API endpoints (annotation CRUD, codebook CRUD, import, agreement, native file pickers)
- `src/ace/templates/` — Jinja2 templates: `base.html`, `landing.html`, `import.html`, `coding.html`, `agreement.html`, `agreement_results.html`
- `src/ace/static/css/` — `ace.css` (design tokens + shared), `coding.css` (coding page), `agreement.css` (agreement page)
- `src/ace/static/js/` — `bridge.js` (client interactivity), vendored `htmx.min.js`, `idiomorph-ext.min.js`, `Sortable.min.js`
- `src/ace/models/` — SQLite CRUD (annotation, codebook, project+coder, source, assignment)
- `src/ace/services/` — business logic (undo, importer, exporter, agreement, coding_render, text_splitter)
- `src/ace/db/` — schema, migrations, connection management
- `.ace` files are SQLite databases with application_id `0x41434500`
- `brand/` — logo SVGs (outside `src/`, not packaged into binary). Source of truth for brand assets
- `src/ace/static/logo.svg` — white tiles on dark (app icon contexts)
- `src/ace/static/logo-light.svg` — dark tiles on white (landing page, docs)
- `src/ace/static/favicon.svg` — tri-colour bar only (16px contexts)

## Running
- `uv run ace` — start server on http://127.0.0.1:8080
- `uv run uvicorn ace.app:create_app --factory --host 127.0.0.1 --port 8080 --reload --reload-dir src/ace` — dev server with hot reload
- `uv run pytest` — run tests (244 tests)
- `uv run pytest tests/path/test_file.py::test_name -v` — run a single test
- `uv build` — build wheel

## Key Gotchas
- `jinja2-fragments` `render_block(env, template, block, context_dict)` returns the FULL block HTML including wrapper divs — use `outerHTML` swap, not `innerHTML`, to avoid nesting
- For OOB swaps, inject `hx-swap-oob="outerHTML"` into the block's own root element via string replace (`_inject_oob()`) — don't wrap in an extra div
- `get_db` is a generator dependency — error paths must `raise HtmxRedirect()`, never `return Response()` (mixing return/yield is invalid)
- CSRF middleware must allow both `http://127.0.0.1` and `http://localhost` origins
- When using `--reload` mode, `_ALLOWED_ORIGINS` must auto-detect from the request (run() isn't called)
- HTMX DELETE sends params as query strings, not form body — use `Query()` not `Form()`
- `hx-sync="this:queue all"` on `#coding-workspace` serialises all server requests — prevents annotation loss on rapid keypresses
- Native file picker endpoints run `osascript` via `asyncio.to_thread()` — blocks without it
- `app.state.project_path` (not session cookie) holds the current project — single-user local app
- `timeout` command not available on macOS — use `& sleep N` pattern instead
- Jinja2's `tojson` filter wraps output in `Markup()` — `| e` after `| tojson` is a no-op. For HTML attributes, pre-escape in Python with `Markup(html.escape(json.dumps(...)))`
- `::highlight()` pseudo-elements do NOT support CSS custom properties (`var()`) cross-browser — use literal alpha values
- Toast uses `X-ACE-Toast` response header — the ONLY working toast mechanism. `HX-Trigger` with `ace-toast` was dead code and has been removed.
- `annotator.css` was deleted (never loaded). CSS for agreement page is in `agreement.css`; coding page in `coding.css`
- HTMX OOB swaps destroy DOM elements — click handlers MUST use event delegation on `document` (not bind to specific elements) to survive swaps
- `_clearSearchFilter()` must dispatch `new Event("input", { bubbles: true })` — just clearing the value doesn't restore hidden rows
- Keycaps q, x, z are reserved (repeat, delete-annotation, undo) — `_KEYCAP_LABELS` array skips them
- Don't nest `role="button"` inside `role="treeitem"` — ARIA violation. Use event delegation + `title` for clickable spans inside treeitems
- `htmx:afterSettle` fires with the PRIMARY swap target, not OOB targets — when `_render_full_coding_oob` swaps `#text-panel` (primary) + `#code-sidebar` (OOB), `evt.detail.target.id` is `"text-panel"`. Must call `_updateKeycaps()` and `_restoreCollapseState()` in the text-panel afterSettle branch too.
- `htmx:beforeSwap` guard must include `text-panel` alongside `code-sidebar` and `coding-workspace` — otherwise sidebar focus state isn't saved before OOB sidebar re-render during flag/navigate
- Colour picker opens via right-click (`contextmenu` event) on code row — was dot click, dots removed
- Source name + flag button now in text panel nav (`.ace-nav-cluster`), not a header bar
- Text panel element is `<main>` (not `<div>`), sidebar is `<aside>` with `role="banner"` branding section
- Version lives in two files: `src/ace/__init__.py` (Python, source of truth for hatchling) and `desktop/src-tauri/Cargo.toml` (desktop). `pyproject.toml` reads from `__init__.py` via `dynamic = ["version"]`; `tauri.conf.json` has no version (falls back to Cargo.toml)

## CSS Design System
- 33 design tokens in `:root` — see ace.css header block
- All classes prefixed `ace-` (e.g., `ace-code-row`, `ace-sentence`, `ace-code-chip`)
- Font size tokens: `--ace-font-size-*` (NOT `--ace-text-*` — that prefix is colours)
- Spacing: 4px grid via `--ace-space-1` (4px) through `--ace-space-8` (32px)
- Sidebar width: `--ace-sidebar-width` CSS variable, persisted via localStorage, set in `<head>` before CSS loads to prevent layout glitch
- Coding page CSS in separate `coding.css`, loaded only on `/code`
- Annotation colours: `::highlight(ace-hl-{code_id})` CSS rules generated in `<style id="code-colours">` block + `_render_colour_style_oob()` for OOB updates
- Borders: `var(--ace-border)` everywhere. Transitions: `var(--ace-transition)` for all interactive elements
- Monochrome slate theme — annotation palette colours are the only hue
- Logo: "Blocks + Bar" — three square tiles (A C E) + Okabe-Ito colourblind-safe bar: Vermillion #D55E00, Sky Blue #56B4E9, Yellow #F0E442
- Logo tiles: #ffffff on dark / #1a1d27 on white. Font: Plus Jakarta Sans 800

## Coding Page Architecture
- **Three-column layout**: sidebar | resize-handle | scroll-wrapper (text panel only)
- **Sentence-based rendering**: `text_splitter.py` (pySBD) splits source text into sentence units; `coding_render.py` renders `<span class="ace-sentence">` elements with `data-start`/`data-end` character offsets
- **CSS Custom Highlight API**: annotation highlights painted client-side via `_paintHighlights()` in bridge.js — creates Range objects from annotation offsets, registers via `CSS.highlights.set("ace-hl-{code_id}", highlight)`. Seamlessly spans across sentence boundaries
- **Annotation data**: passed to client via hidden `<div id="ace-ann-data" data-annotations="...">` element, updated via OOB swap
- **Bottom code bar**: sticky bar at bottom of text panel showing applied codes as coloured text chips. Click flashes the annotated text using a temporary `CSS.highlights.set("ace-flash", ...)` highlight
- **Sidebar**: `<aside>` with branding row (ACE + ? help, 32px) at top. ARIA treeview with roving tabindex. Left-border colour stripes (3px) per code row, 28px row height, no dots. Group collapse via `aria-expanded`. Collapse state in `_collapsedGroups`, restored after OOB swaps. "Codebook ▾" dropdown menu for import/export. Right-click context menu has "New Group…" in Move to Group submenu.
- **Keyboard shortcuts**: 1-9/0/a-p/r-w/y apply codes (q/x/z reserved), ↑/↓ navigate sentences, Shift+←/→ navigate sources, Q repeat, Z undo, X delete, / opens search, Tab cycles zones (text→search→tree)
- **Code application**: keycap badge click (mouse), keycap hotkey (keyboard), search Enter (first match), tree Enter (focused code). All paths use `_applyCode()` helper which supports custom selection and announces to aria-live region

## HTMX Patterns
- Templates use `{% block name %}` regions that `jinja2-fragments` renders independently
- Coding page swap zones: `#code-sidebar`, `#text-panel`, `#source-grid-overlay`, `#ace-ann-data`, `<style id="code-colours">`
- Annotation actions use `htmx.ajax()` directly (not hidden trigger buttons) to avoid `hx-sync` queue timing issues
- Dialogs: native `<dialog>` loaded into `#modal-container` via HTMX, auto-opened by bridge.js `htmx:afterSettle`
- Toast: `X-ACE-Toast` response header — bridge.js `htmx:afterRequest` handler calls `aceToast()`
- Never use HTTP 302 for HTMX — use `HX-Redirect` header via `HtmxRedirect` exception
- OOB assembly helpers in api.py: `_render_coding_oob()` (text panel + ann data), `_render_full_coding_oob()` (all zones), `_render_sidebar_and_text()` (sidebar + text + colours + ann data)

## Code Style
- Reusable JS in `bridge.js` — avoid inline `<script>` except for page-specific state init
- `_coding_context()` in pages.py assembles all template data — reused by all coding routes
- Colour values validated with `re.fullmatch(r'#[0-9a-fA-F]{6}', colour)` before storage
- Escape user-controlled text with `html.escape()` before interpolating into HTML
- `_require_coder_id(request)` in api.py — use instead of repeating the `getattr` + `if None` guard
- `_tk_root()` in api.py — shared tkinter root setup for file picker fallbacks
- `_build_counts()` / `_observed_agreement()` in agreement_computer.py — shared helpers for kappa functions

## Workflow
- Conventional commit style (`feat`, `fix`, `style`, `refactor`, `test`, `build`, `docs`). Plain British English.
- **On feature branches:** commit freely at whatever granularity helps (small commits for safety/undo are fine)
- **Merging to main:** squash merge — one clean commit per feature. `git merge --squash feat/branch && git commit` or `gh pr merge N --squash --delete-branch`
- **Large features with distinct phases:** interactive rebase to 2-3 logical commits, then fast-forward merge (rare)
- **Small fixes/refactors:** commit directly on main, no branch needed
- **Main history should read like a changelog** — one `feat:`/`fix:` per logical change, no iteration noise

## Landing Page
- Simplified layout: logo → subtitle → conditional resume link → New project / Open file → Tools
- Resume link reads first entry from `ace-recent-files` localStorage — shows filename only (no label), subtle underline, dismiss × on hover
- No coder name step in new project flow — API defaults to `"default"`
- New project flow: type name → Enter → native folder picker → project created
- `sips` cannot render SVG — Tauri master icon.png (1024×1024) generated via HTML→browser screenshot, then `sips` resizes to all icon sizes

## Agreement
- Streamlined flow: choose files → auto-compute → results page (no intermediate steps)
- Overall metric uses pooled computation (not macro-average) — concatenate per-code vectors, compute once
- Pairwise returns full `CodeMetrics` per pair (not just alpha)
- Results cached on `app.state.agreement_dataset` / `app.state.agreement_result` — exports read from cache
- References sourced from `src/ace/static/agreement_references.bib`
- Raw data export: long-form span CSV (`source_id, start_offset, end_offset, coder_id, code_name`)
- Server auto-kills stale instances on startup via `_kill_stale_server()`
- TestClient must use context manager (`with TestClient(app) as c:`) for lifespan to run
- `httpx` in dev dependencies for TestClient

## Desktop Release (Tauri)
- `desktop/` — Tauri v2 desktop wrapper, sidecar architecture
- `scripts/build_sidecar.py` — Nuitka onefile compile, called by Tauri's `beforeBuildCommand`
- Sidecar binary must exist at `desktop/src-tauri/binaries/ace-server-{triple}` before Rust compile — `beforeBuildCommand` (not `beforeBundleCommand`) is critical
- Release workflow: bump version in `__init__.py` + `desktop/src-tauri/Cargo.toml` → push to main → `git tag v0.x.x && git push origin v0.x.x` → CI builds + creates draft release
- CI triggers on `v*` tags only (`.github/workflows/release.yml`) — regular pushes to main do NOT build desktop binaries
- `_preview_fragment()` in api.py — shared HTML builder for import preview (used by both `import_folder` and `import_preview` endpoints)
