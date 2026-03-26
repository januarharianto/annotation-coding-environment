# Contributing to ACE

Thanks for your interest in contributing. This guide covers how we work together on this project.

## Setting up

You'll need [uv](https://docs.astral.sh/uv/) installed. Then:

```bash
git clone https://github.com/januarharianto/annotation-coding-environment.git
cd annotation-coding-environment
uv sync
```

To run the app locally: `uv run ace` (opens at http://127.0.0.1:8080).
To run the tests: `uv run pytest`.

## How we work with branches

The `main` branch should always be in a working state. Don't push broken code to it.

For anything beyond a trivial fix, create a branch first. We use prefixes to keep things tidy:

- `feat/` for new features (e.g. `feat/grouped-codes`)
- `fix/` for bug fixes (e.g. `fix/44-text-overflow`)
- `refactor/` for internal restructuring

For genuinely small changes — a typo, a one-line config tweak — committing straight to `main` is fine.

## Writing commit messages

We follow [conventional commits](https://www.conventionalcommits.org/). In short, start the first line with a prefix like `feat:`, `fix:`, `refactor:`, etc., followed by a brief summary in plain English. If you want to explain the reasoning, add a longer description after a blank line.

Example:

```
feat(codebook): add group support to CSV import

Read the optional 'group' column from CSV files and store as
group_name on each code. Colours are always auto-assigned.
```

The common prefixes are: `feat`, `fix`, `style`, `refactor`, `test`, `build`, `docs`.

## Pull requests

Open a pull request for each piece of work. Keep it to one logical change — don't bundle unrelated things together.

Write the PR title in the same conventional commit format as above, because when we merge it becomes the commit message on `main`. We squash merge everything:

```bash
gh pr merge N --squash --delete-branch
```

Then switch back to main and pull: `git checkout main && git pull`.

## Testing

Please make sure all tests pass before you push. Run `uv run pytest` and check.

If you're adding new behaviour, write a test for it. If you're fixing a bug, write a test that reproduces it first, then fix it.

## Releasing a new version

We use semantic versioning. While the project is pre-release, versions look like `0.MINOR.PATCH` — bump the minor number for features, the patch number for fixes.

To release:

1. Add a new section at the top of `CHANGELOG.md` describing what changed
2. Commit it: `git commit -am "docs: changelog for v0.2.0"`
3. Tag it: `git tag v0.2.0`
4. Push both: `git push && git push --tags`
5. Create the GitHub release: `gh release create v0.2.0 --notes-from-tag`

### Writing the changelog

The changelog is for users, not developers. Only mention things that someone using the app would notice or care about. Internal refactors, test changes, and code cleanup don't belong here.

Use these categories:

- **Added** — new features or capabilities
- **Changed** — existing behaviour that works differently now
- **Fixed** — bugs that were resolved
- **Removed** — features or options that were taken out

Example:

```markdown
## 0.2.0

### Added
- Grouped codes with collapsible sidebar headers

### Changed
- CSV import simplified — colour column removed

### Fixed
- Source panel no longer expands when annotating long text (#44)
```

## Project layout

```
src/ace/
├── app.py              — app entry point and server config
├── pages/              — page routes and UI
│   ├── landing.py      — home page (/)
│   ├── import_page.py  — source import (/import)
│   ├── coding.py       — main coding interface (/code)
│   ├── coding_*.py     — extracted modules (actions, dialogs, shortcuts, etc.)
│   └── header.py       — shared header bar
├── models/             — database operations (one file per table)
├── services/           — business logic (palette, undo, agreement, etc.)
├── db/                 — schema, migrations, connection management
└── static/             — JavaScript and CSS
```

## Code conventions

A few things to know if you're working in the code:

- The UI is built with [NiceGUI](https://nicegui.io/) and uses Quasar component classes for layout (things like `q-pa-md`, `full-width`, `items-center`)
- Custom CSS classes are prefixed with `ace-` (e.g. `ace-annotation`, `ace-group-header`)
- Data is stored in `.ace` files, which are SQLite databases
- The colour scheme is monochrome — near-black primary (`#212121`), grey borders (`#bdbdbd`). The only colour in the app comes from the annotation palette.
