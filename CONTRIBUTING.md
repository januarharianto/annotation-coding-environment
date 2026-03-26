# Contributing to ACE

## Getting Started

```bash
git clone https://github.com/januarharianto/annotation-coding-environment.git
cd annotation-coding-environment
uv sync          # install dependencies
uv run ace       # start dev server on http://127.0.0.1:8080
uv run pytest    # run tests
```

## Branching

- `main` is always deployable
- Create a branch for any non-trivial change:
  - `feat/description` — new features
  - `fix/description` or `fix/42-short-title` — bug fixes (reference the issue number)
  - `refactor/description` — internal restructuring
- Tiny one-liner fixes (typos, config) can go straight to `main`

## Commits

Use [conventional commits](https://www.conventionalcommits.org/). Plain British English. A description body is welcome for context.

```
feat(codebook): add group support to CSV import

Read the optional 'group' column from CSV files and store as
group_name on each code. Colours are always auto-assigned.
```

Prefixes: `feat`, `fix`, `style`, `refactor`, `test`, `build`, `docs`

## Pull Requests

- One PR per logical change
- PR title in conventional commit format (it becomes the squash commit message)
- Squash merge: `gh pr merge N --squash --delete-branch`
- After merge: `git checkout main && git pull`

## Testing

- Write tests before or alongside implementation
- Run `uv run pytest` before pushing
- All tests must pass before merging

## Releasing

1. Update `CHANGELOG.md` with a new version section (see format below)
2. Commit: `git commit -am "docs: changelog for vX.Y.Z"`
3. Tag: `git tag vX.Y.Z`
4. Push: `git push && git push --tags`
5. Create release: `gh release create vX.Y.Z --notes-from-tag`

Versioning: `0.MINOR.PATCH` while pre-release. Bump minor for features, patch for fixes.

### Changelog format

Write for users, not developers. Only include what someone using the app would care about.

```markdown
## 0.2.0

### Added
- Grouped codes with collapsible sidebar headers

### Changed
- CSV import simplified — colour column removed

### Fixed
- Source panel no longer expands when annotating long text (#44)
```

Categories: **Added**, **Changed**, **Fixed**, **Removed**.

## Code Style

- NiceGUI + Quasar for UI — use Quasar classes for layout (`q-pa-md`, `full-width`)
- Custom CSS classes prefixed with `ace-` (e.g. `ace-annotation`, `ace-group-header`)
- SQLite for storage — `.ace` files are SQLite databases
- No colour in CSV imports — always auto-assigned from palette
- Borders: `#bdbdbd`. Transitions: `0.15s`. Primary colour: `#212121` (near-black)

## Project Structure

```
src/ace/
├── app.py              # NiceGUI app entry point
├── pages/              # page routes and UI
│   ├── landing.py      # / — home page
│   ├── import_page.py  # /import — source import
│   ├── coding.py       # /code — main coding interface
│   ├── coding_*.py     # extracted modules (actions, dialogs, shortcuts, etc.)
│   └── header.py       # shared header bar
├── models/             # SQLite CRUD operations
├── services/           # business logic (palette, undo, agreement, etc.)
├── db/                 # schema, migrations, connection management
└── static/             # JS and CSS assets
```
