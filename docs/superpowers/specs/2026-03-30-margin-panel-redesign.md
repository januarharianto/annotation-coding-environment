# Margin Panel Redesign — Spec

## Goal

Replace the current stacked-list margin panel with positionally-aligned floating cards that show which codes are applied where, aligned vertically to the coded text.

## Current State

The margin panel is a 200px right column showing a flat list of annotation notes (code name + 40-char text preview + colour bar + merge count). Notes are not positionally aligned — they stack from the top regardless of where the annotation sits in the text. Click navigates to the sentence.

## Design Decisions

- **Floating cards** positioned at the vertical midpoint of each annotation's sentence range
- **Code dot + name only** — no text preview (redundant with inline highlights)
- **Overlap grouping** — multiple codes covering the same sentence(s) merge into one card with stacked dot+name rows
- **Click → yellow flash** — clicking a card briefly flashes the coded sentences (browser "Find on Page" style yellow pulse, ~1s), without changing keyboard focus
- **No scroll sync** — the margin panel scrolls independently (adequate for typical source lengths)

## Architecture

### Data Flow (unchanged)

`build_margin_annotations()` in `coding_render.py` already groups adjacent same-code annotations by sentence index. The existing data structure (`code_id`, `code_name`, `colour`, `start_idx`, `end_idx`) provides most of what's needed. A minor extension merges groups that cover the exact same sentence range into a single entry with multiple codes (for overlap grouping in the card UI).

### Template Changes (`coding.html`)

The `{% block margin_panel %}` renders one card per annotation group. Each card has `data-start-idx` and `data-end-idx` attributes (already present). The card content changes from code name + text preview to just code dot + code name.

For overlap grouping: annotations that share the same `start_idx`/`end_idx` range are rendered as multiple rows within a single card. This grouping happens server-side in `build_margin_annotations()` — extend it to merge groups with identical sentence ranges into a single entry with multiple codes.

### CSS Changes (`coding.css`)

- Cards use `position: absolute` within the margin panel (which becomes `position: relative`)
- Each card's `top` is set by JS based on the corresponding sentence's vertical position
- Card style: white background, subtle border, small border-radius, compact padding
- Code dot (8px circle) + code name in each row
- Yellow flash keyframe animation on `.ace-sentence` (reusable class `ace-flash`)

### JS Changes (`bridge.js`)

**`_positionMarginCards()`** — reads each card's `data-start-idx`/`data-end-idx`, finds the corresponding sentence elements, computes vertical midpoint, sets `card.style.top`. Runs on:
- `DOMContentLoaded` (initial load)
- `htmx:afterSettle` for `text-panel` or `coding-workspace` targets
- `window.resize`

**Anti-collision** — if two cards would overlap vertically, nudge the lower one down by the overlap amount. Simple single-pass top-to-bottom.

**Click handler** — clicking a margin card:
1. Finds sentence elements from `data-start-idx` to `data-end-idx`
2. Scrolls the first sentence into view (`scrollIntoView({ block: 'nearest' })`)
3. Adds `ace-flash` class to each sentence
4. Removes class after animation completes (~1.2s)

### Overlap Grouping

Annotations covering the exact same sentence range merge into one card. For example, if "Used AI" covers sentences 0-1 and "Helpful" also covers sentences 0-1, they share one card:

```
[ ● Used AI   ]
[ ● Helpful   ]
```

Annotations with different ranges get separate cards, even if they overlap partially. For example, "Used AI" on sentences 0-1 and "Helpful" on sentences 1-2 get two separate cards positioned at their respective midpoints.

### Flash Animation

```css
@keyframes ace-flash {
  0% { background: rgba(255, 235, 59, 0.7); }
  100% { background: transparent; }
}
.ace-flash {
  animation: ace-flash 1.2s ease-out;
}
```

The flash applies to `.ace-sentence` elements. Since highlights are painted by the CSS Custom Highlight API (not the sentence background), the yellow flash sits underneath the highlight and creates a visible pulse without interfering with annotation colours.

## Files to Change

| File | Change |
|------|--------|
| `src/ace/services/coding_render.py` | Extend `build_margin_annotations()` to merge same-range groups |
| `src/ace/templates/coding.html` | Rewrite `margin_panel` block — dot+name cards, no text preview |
| `src/ace/static/css/coding.css` | New card styles, absolute positioning, flash animation |
| `src/ace/static/js/bridge.js` | `_positionMarginCards()`, click-flash handler, resize listener |

## What's Removed

- 40-character text preview in margin notes
- "N sentences merged" badge
- Current stacked-list layout (replaced by positioned cards)

## What's Preserved

- `build_margin_annotations()` data pipeline (extended, not replaced)
- Click interactivity (flash instead of focus)
- Colour-coded left indicator (dot instead of bar)
- OOB swap mechanism for margin panel updates
