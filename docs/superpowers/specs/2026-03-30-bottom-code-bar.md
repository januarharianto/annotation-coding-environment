# Bottom Code Bar — Spec

## Goal

Replace the right margin panel with a sticky bottom code bar showing clickable code chips. Clicking a chip flashes that code's sentences in the code's own colour.

## Current State

The right margin panel shows floating cards positionally aligned to coded text. It requires JS positioning (`_positionMarginCards`, `_schedulePosition`, ResizeObserver), overlap resolution, height syncing, and a 180px-wide column. The margin panel is updated via OOB swap on every annotation action.

## Design

### Bottom Code Bar

A thin horizontal bar sticky at the bottom of the text scroll area. Shows one chip per code applied to this source. Each chip has a colour dot + code name on a neutral background. When no annotations exist, the bar is hidden.

The bar uses `position: sticky; bottom: 0` inside the text panel so it remains visible while scrolling through long sources.

### Chip Style

Chips have neutral backgrounds (not colour-tinted) with a coloured dot, matching the sidebar code row pattern. This avoids readability issues with coloured backgrounds and keeps the design consistent.

```html
<span class="ace-code-chip" data-code-id="..." data-colour="#e53935">
  <span class="ace-code-chip-dot" style="background: #e53935;"></span>
  Used AI
</span>
```

### Chip Click → Colour Flash

Clicking a chip:
1. Reads `data-code-id` from the chip
2. Reads annotation data from `#ace-ann-data` (already in the DOM for the CSS Highlight API)
3. For each annotation matching this code_id, finds overlapping sentences via `data-start`/`data-end` attribute comparison (linear scan — fine for <1000 sentences)
4. Scrolls the first matching sentence into view
5. Flashes each sentence with the code's own colour:

```javascript
el.style.transition = 'none';
el.style.background = 'rgba(r,g,b,0.5)';  // snap to strong colour
void el.offsetWidth;                        // force reflow
el.style.transition = 'background 1.2s ease-out';
el.style.background = '';                   // clear inline → CSS class reasserts
```

Setting `el.style.background = ''` removes the inline style entirely, so any CSS class background (e.g. `ace-sentence--focused`) reasserts correctly after the flash. The colour RGB values are stored as `data-colour` on the chip.

### Data

The bar needs a deduplicated list of codes applied to this source: `{code_id, code_name, colour}`. This replaces the complex `build_margin_annotations()` grouping with a simple dedup of annotation code_ids.

### Template

The code bar sits inside `{% block text_panel %}`, after the sentence content. It re-renders automatically on every annotation HTMX swap (part of the text_panel block).

### CSS

```css
.ace-code-bar {
  position: sticky;
  bottom: 0;
  padding: var(--ace-space-2) var(--ace-space-4);
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
  border-top: 1px solid var(--ace-border-light);
  background: var(--ace-bg);
  z-index: 1;
}

.ace-code-bar-label {
  font-size: var(--ace-font-size-2xs);
  color: var(--ace-text-muted);
}

.ace-code-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid var(--ace-border-light);
  border-radius: 10px;
  font-size: var(--ace-font-size-xs);
  cursor: pointer;
  background: var(--ace-bg);
  color: var(--ace-text);
  transition: background 0.15s;
}

.ace-code-chip:hover {
  background: var(--ace-bg-muted);
}

.ace-code-chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
```

## What Gets Deleted

- `{% block margin_panel %}` template block (the floating cards)
- All `.ace-margin-*` CSS rules (~57 lines)
- `@keyframes ace-flash` and `.ace-flash` CSS rules
- `_positionMarginCards()`, `_schedulePosition()`, `_positionRafPending` in bridge.js
- ResizeObserver on `#content-scroll` for margin positioning
- `_schedulePosition()` calls in afterSettle, pointerup, DOMContentLoaded
- Click-flash handler on `.ace-margin-note`
- `build_margin_annotations()` in `coding_render.py`
- 9 tests for `build_margin_annotations` in `tests/test_services/test_coding_render.py`
- `margin_annotations` from `_coding_context()` in pages.py
- OOB margin panel rendering in `_render_coding_oob`, `_render_full_coding_oob`, `_render_sidebar_and_text`
- Margin panel column (180px `flex-shrink: 0`) — text panel gets full width

## What Gets Added

- Bottom code bar template inside `text_panel` block with `position: sticky; bottom: 0`
- `.ace-code-bar`, `.ace-code-chip` CSS (~30 lines)
- Chip click handler with colour flash (~25 lines JS)
- `margin_codes` computation in `_coding_context()` — simple dedup (~8 lines)

## What Stays Unchanged

- CSS Custom Highlight API for persistent annotation highlights
- `#ace-ann-data` hidden div with annotation JSON (used by both highlights and chip flash)
- `#content-scroll` shared scroll wrapper (one child now — text panel only)
- All annotation CRUD endpoints
- Keyboard shortcuts, sidebar, navigation

## Files to Change

| File | Change |
|------|--------|
| `src/ace/services/coding_render.py` | Delete `build_margin_annotations()` |
| `tests/test_services/test_coding_render.py` | Delete `build_margin_annotations` tests |
| `src/ace/templates/coding.html` | Remove `margin_panel` block, add code bar inside `text_panel` block |
| `src/ace/static/css/coding.css` | Remove `.ace-margin-*` and `ace-flash` rules, add `.ace-code-bar`/`.ace-code-chip` rules |
| `src/ace/static/js/bridge.js` | Remove positioning JS + margin click handler, add chip click-flash handler |
| `src/ace/routes/pages.py` | Replace `margin_annotations` with `margin_codes` (deduped code list) |
| `src/ace/routes/api.py` | Remove margin panel from all 3 OOB helpers |
