# Bottom Code Bar — Spec

## Goal

Replace the right margin panel with a bottom code bar showing clickable code chips. Clicking a chip flashes that code's sentences in the code's own colour.

## Current State

The right margin panel shows floating cards positionally aligned to coded text. It requires JS positioning (`_positionMarginCards`, `_schedulePosition`, ResizeObserver), overlap resolution, height syncing, and a 180px-wide column. The margin panel is updated via OOB swap on every annotation action.

## Design

### Bottom Code Bar

A thin horizontal bar at the bottom of the text content (inside the scroll wrapper, below the last sentence). Shows one chip per code applied to this source. Each chip has a colour dot + code name, styled with a tinted background matching the code's colour.

When no annotations exist, the bar is hidden (no "No annotations yet" placeholder — the bar simply doesn't render).

### Chip Click → Colour Flash

Clicking a chip:
1. Finds all sentences annotated with that code (by matching annotation offsets to sentence `data-start`/`data-end`)
2. Scrolls the first matching sentence into view
3. Flashes the sentences with the code's own colour: background snaps to `rgba(r,g,b,0.5)`, then fades back to transparent over 1.2s via CSS transition

The flash uses the sentence element's `background` property (separate layer from the CSS Custom Highlight API paint). No CSS keyframe animation needed — inline transition handles it.

### Data

The bar needs: which codes are applied to this source, with their colours. This is already available from `margin_annotations` (the grouped annotation list). Simplify it: just need a deduplicated list of `{code_id, code_name, colour}` for all codes on this source, plus the annotation offsets for the flash.

Rewrite `build_margin_annotations()` to return a simpler structure — or replace it with a new function that returns what the bottom bar needs.

Actually, the annotation data for flash (which sentences to highlight) is already in `#ace-ann-data` (the hidden div with annotation JSON for the CSS Highlight API). The bottom bar just needs the unique codes list. The flash handler can read `#ace-ann-data` to find matching annotations and map them to sentences.

### Template

Replace the `{% block margin_panel %}` with a bottom bar inside the text panel, after the sentence content:

```html
{% if margin_codes %}
<div class="ace-code-bar">
  <span class="ace-code-bar-label">Codes:</span>
  {% for code in margin_codes %}
  <span class="ace-code-chip" data-code-id="{{ code['code_id'] }}"
        style="background: rgba({{ code.r }},{{ code.g }},{{ code.b }},0.1);
               border-color: rgba({{ code.r }},{{ code.g }},{{ code.b }},0.2);
               color: {{ code['colour'] }};">
    <span class="ace-code-chip-dot" style="background: {{ code['colour'] }};"></span>
    {{ code['code_name'] }}
  </span>
  {% endfor %}
</div>
{% endif %}
```

### CSS

```css
.ace-code-bar {
  padding: var(--ace-space-2) var(--ace-space-4);
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
  border-top: 1px solid var(--ace-border-light);
  margin-top: var(--ace-space-4);
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
  border: 1px solid;
  border-radius: 10px;
  font-size: var(--ace-font-size-xs);
  cursor: pointer;
  transition: filter 0.15s;
}

.ace-code-chip:hover {
  filter: brightness(0.95);
}

.ace-code-chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
```

### JS — Flash Handler

Click handler on `.ace-code-chip`:
1. Read `data-code-id` from the chip
2. Read annotation data from `#ace-ann-data`
3. For each annotation matching this code_id, find overlapping sentences
4. Flash each sentence: snap background to `rgba(r,g,b,0.5)`, transition back over 1.2s
5. Scroll first sentence into view

The colour RGB values can be extracted from the chip's inline `style` attribute, or stored as `data-r`, `data-g`, `data-b` attributes.

## What Gets Deleted

- `{% block margin_panel %}` template block (the floating cards)
- All `.ace-margin-*` CSS rules
- `_positionMarginCards()`, `_schedulePosition()`, `_positionRafPending` in bridge.js
- ResizeObserver on `#content-scroll` for margin positioning
- `_schedulePosition()` calls in afterSettle, pointerup, DOMContentLoaded
- Click-flash handler on `.ace-margin-note`
- `build_margin_annotations()` in `coding_render.py` (replace with simpler `get_source_codes()`)
- `margin_annotations` from `_coding_context()` in pages.py
- OOB margin panel rendering in `_render_coding_oob`, `_render_full_coding_oob`, `_render_sidebar_and_text`
- Margin panel grid column (180px `flex-shrink: 0`) — text panel gets full width

## What Gets Added

- Bottom code bar template (inside text panel block)
- `.ace-code-bar`, `.ace-code-chip` CSS (~25 lines)
- Chip click handler with colour flash (~20 lines JS)
- `get_source_codes()` helper in pages.py or coding_render.py (~10 lines)

## What Stays Unchanged

- CSS Custom Highlight API for persistent annotation highlights
- `#ace-ann-data` hidden div with annotation JSON
- `#content-scroll` shared scroll wrapper (text panel still inside it, but margin panel removed — wrapper now has just one child)
- All annotation CRUD endpoints
- Keyboard shortcuts, sidebar, navigation

## Files to Change

| File | Change |
|------|--------|
| `src/ace/services/coding_render.py` | Replace `build_margin_annotations()` with simpler `get_source_codes()` |
| `src/ace/templates/coding.html` | Remove `margin_panel` block, add code bar inside `text_panel` block |
| `src/ace/static/css/coding.css` | Remove `.ace-margin-*` rules, add `.ace-code-bar`/`.ace-code-chip` rules |
| `src/ace/static/js/bridge.js` | Remove positioning JS, add chip click-flash handler |
| `src/ace/routes/pages.py` | Replace `margin_annotations` with `margin_codes` in context |
| `src/ace/routes/api.py` | Remove margin panel from OOB helpers |

## Net Effect

Significant code reduction. The margin panel positioning system (~80 lines JS) is replaced by a ~20 line click handler. The floating card CSS (~50 lines) is replaced by ~25 lines of chip styles. Server-side grouping logic simplifies from overlap-aware merge to a simple dedup.
