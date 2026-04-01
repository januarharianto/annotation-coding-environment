# Top Bar Redesign

**Date:** 2026-04-01
**Branch:** `feat/top-bar-redesign`

## Overview

Replace the current disjointed coding page header (Home, project name, progress %, Export, coder name) with a focused, minimal top bar centred on source identity. The bar answers one question: "What am I coding right now?"

## Layout

```
ACE          Interview_07  3 / 20  [⚑ Flagged]          ?
└─left       └──────────── centre ─────────────┘    right─┘
```

Three zones: left (brand/home), centre (source context), right (help).

## Semantic HTML

The outer container changes from `<div>` to `<header>` for the banner landmark. All interactive elements use semantic elements (`<a>`, `<button>`) — no clickable `<span>` or `<div>`.

## Elements

### ACE wordmark (left)

- `<a href="/">` with text "ACE"
- Styled text: `font-weight: 700`, `--ace-font-size-sm` (12px), tight letter-spacing (-0.3px), `--ace-text-muted` colour
- Hover: `color: var(--ace-text)`, `transition: color var(--ace-transition)`
- Focus: `:focus-visible` outline using `var(--ace-focus)`
- Replaces the old "← Home" link

### Source name (centre)

- Template expression: `{{ current_source.display_id }}`
- `font-weight: 600`, `--ace-font-size-base` (14px), `--ace-text` colour — the hero element, largest text in the bar
- Truncation: `max-width: 30ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap`
- `title="{{ current_source.display_id }}"` for hover tooltip on long names
- Guard: `{{ current_source.display_id if current_source else '' }}`

### Position counter (text panel navigation only)

- Not in the header — lives in the existing text panel source navigation cluster
- Avoids duplication between header and text panel

### Flag indicator (centre, after source name)

- `<button>` element with `aria-label="Toggle flag"` and `aria-pressed="true|false"`
- **Unflagged:** `⚑` icon in `var(--ace-text-muted)` colour, no background
- **Flagged:** `⚑ Flagged` chip — background `rgba(191, 54, 12, 0.1)`, colour `#bf360c` (Material deepOrange 900 — passes WCAG AA at 7.8:1 on white), border `1px solid rgba(191, 54, 12, 0.25)`, border-radius `var(--ace-radius)`, font-size `--ace-font-size-2xs`, font-weight `600`
- Hover (unflagged): `color: var(--ace-text)`
- Hover (flagged): `background: rgba(191, 54, 12, 0.16)`
- Focus: `:focus-visible` outline using `var(--ace-focus)`
- Click triggers the existing flag toggle endpoint via `htmx.trigger(document.getElementById("trigger-flag"), "click")`
- After toggle, `_announce()` is called: "Source flagged" / "Source unflagged"
- Toast feedback via `X-ACE-Toast` response header: `"Source flagged"` / `"Source unflagged"`
- Known behaviour: unflagging sets status to `in_progress` regardless of previous status (existing API behaviour — not changed in this redesign)

### ? help button (right)

- `<button>` element with `aria-label="Keyboard shortcuts"`
- `?` character, `--ace-text-muted` colour
- Hover: `color: var(--ace-text)`, `transition: color var(--ace-transition)`
- Focus: `:focus-visible` outline using `var(--ace-focus)`
- Click calls `_toggleCheatSheet()` — this function is currently private inside bridge.js's IIFE, so either expose it on `window` or add the click listener inside the IIFE

## Removed from header

| Element | Where it goes |
|---------|--------------|
| Project name | Visible on landing page only. Not needed during coding. |
| Progress % (`complete_pct`) | Replaced by position counter "3 / 20". |
| Export link | Moves to landing page as a project-level action. |
| Coder name | Removed entirely. Not needed during coding. |
| "← Home" text | Replaced by ACE wordmark (same destination). |

## Keyboard access

The existing Tab cycle is: text panel → search bar → code tree → text panel. The header becomes a fourth zone:

```
text panel → header → search bar → code tree → text panel
```

Update `_activeZone()` to detect `#coding-header` focus. The header's `<a>` and `<button>` elements are natively focusable — browser Tab order within the header flows left to right (ACE link → flag button → ? button).

## Behaviour

- **Source navigation:** source name and position counter update on page load when navigating sources (source navigation uses `window.location.href`, which is a full page load)
- **Flag toggle:** clicking the flag button triggers the existing `#trigger-flag` hidden button, which calls `POST /api/code/flag`. The response includes an OOB header swap via `_render_full_coding_oob()`. After the swap, `_announce()` provides screen reader feedback.
- **? button:** click handler calls `_toggleCheatSheet()` (must be exposed or listener added inside bridge.js IIFE)
- **ACE wordmark:** standard `<a href="/">` link, no JavaScript needed
- **Position counter vs text panel counter:** the text panel's existing nav cluster (prev/next arrows + counter) is kept as-is. The header counter is complementary context — glanceable without looking at the text panel. Both show the same value.

## CSS

- Change `.ace-coding-header` container from `<div>` to `<header>` — keep same styles (40px height, flex, border-bottom)
- Left zone: `flex: 0 0 auto`
- Centre zone: `flex: 1; display: flex; align-items: center; justify-content: center; gap: 8px`
- Right zone: `flex: 0 0 auto`
- New classes: `.ace-flag-chip` (flagged state), `.ace-flag-btn` (base button reset + cursor), `.ace-header-help` (? button)
- All interactive elements: `transition: color var(--ace-transition)` + `:focus-visible { outline: 2px solid var(--ace-focus); outline-offset: 2px }`
- Remove unused classes: `.ace-completion`, `.ace-coding-header-title`, `.ace-coding-header-left`, `.ace-coding-header-right`, `.ace-coding-header-back`

## Data requirements

`_coding_context()` in `pages.py` already returns:
- `current_source` — dict with `display_id` key (template: `{{ current_source.display_id }}`)
- `current_index` — 0-based index (template: `{{ current_index + 1 }}`)
- `total_sources` — total source count
- `current_status` — string: "pending", "in_progress", "complete", or "flagged" (template: `{% if current_status == 'flagged' %}`)

No new context keys needed. No new API endpoints needed.

## Scope boundaries

### In scope
- Rebuild `{% block coding_header %}` template with `<header>` element and semantic buttons
- Update CSS for new layout, remove old classes
- Add click handler for flag toggle (reuse existing `#trigger-flag` mechanism)
- Add click handler for ? button (expose `_toggleCheatSheet` or add listener in IIFE)
- Add header as fourth zone in Tab cycle
- Add `_announce()` calls for flag toggle
- Add toast feedback for flag toggle
- Remove old header elements and unused CSS

### Out of scope
- Moving export to landing page (separate task — the link is simply removed from the header)
- Source navigation redesign (prev/next stays in text panel as-is)
- Landing page changes
- Flag toggle status restoration (unflag always sets `in_progress` — existing behaviour)
- New API endpoints
