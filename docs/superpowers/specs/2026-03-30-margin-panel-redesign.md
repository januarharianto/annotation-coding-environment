# Margin Panel Redesign — Spec

## Goal

Replace the current stacked-list margin panel with positionally-aligned floating cards that show which codes are applied where, aligned vertically to the coded text.

## Current State

The margin panel is a 200px right column showing a flat list of annotation notes (code name + 40-char text preview + colour bar + merge count). Notes are not positionally aligned — they stack from the top regardless of where the annotation sits in the text. Click navigates to the sentence.

## Design Decisions

- **Floating cards** positioned at the vertical midpoint of each annotation's sentence range
- **Code dot + name only** — no text preview (redundant with inline highlights)
- **Overlap grouping** — multiple codes covering the same sentence(s) merge into one card with stacked dot+name rows
- **Click → yellow flash** — clicking a card briefly flashes the coded sentences (browser "Find on Page" style yellow pulse, ~1.2s), without changing keyboard focus
- **Shared scroll container** — text panel and margin panel scroll together (no sync JS needed)

## Architecture

### Scroll Container

Wrap the text panel and margin panel in a single scrolling div so that absolutely-positioned margin cards scroll naturally with the text. The current layout has separate `overflow-y: auto` on each panel — change to a shared wrapper.

```
Before:  sidebar | handle | text-panel(scroll) | margin-panel(scroll)
After:   sidebar | handle | scroll-wrapper(scroll) { text-col + margin-col }
```

The scroll wrapper gets `overflow-y: auto`. Inside it, a flex or sub-grid layout places the text column and margin column side by side. The margin column gets `position: relative; overflow: visible;` so absolutely-positioned cards can extend beyond its bounds if needed.

### Data Flow

`build_margin_annotations()` in `coding_render.py` needs two fixes:

1. **Remove the `break`** in the inner loop (line 86) — currently cross-sentence annotations only map to their first overlapping sentence. Removing the `break` maps each annotation to ALL overlapping sentences, giving accurate `start_idx`/`end_idx` ranges.

2. **Change return type for overlap grouping** — the current return type has scalar `code_id`/`code_name`/`colour` fields per group. Change to a `codes: list[dict]` field so a single group can hold multiple codes when annotations share the exact same sentence range.

New return shape per group:
```python
{
    "codes": [
        {"code_id": "...", "code_name": "...", "colour": "#..."},
        ...  # multiple codes if overlapping same range
    ],
    "start_idx": 0,
    "end_idx": 2,
}
```

After building the initial groups (one per annotation, merged by adjacency), a second pass merges groups with identical `(start_idx, end_idx)` keys into a single entry with combined `codes` lists. The `texts` field is dropped (no longer shown in the margin).

### Template Changes (`coding.html`)

The `{% block margin_panel %}` renders one card per group. Each card has `data-start-idx` and `data-end-idx` attributes. The card contains one row per code (dot + name). No text preview, no merge badge.

```html
<div class="ace-margin-note" data-start-idx="0" data-end-idx="2">
  <div class="ace-margin-note-row">
    <span class="ace-margin-dot" style="background: #A91818;"></span>
    <span class="ace-margin-note-code">Used AI</span>
  </div>
</div>
```

For overlap-grouped cards (multiple codes):
```html
<div class="ace-margin-note" data-start-idx="0" data-end-idx="1">
  <div class="ace-margin-note-row">
    <span class="ace-margin-dot" style="background: #A91818;"></span>
    <span class="ace-margin-note-code">Used AI</span>
  </div>
  <div class="ace-margin-note-row">
    <span class="ace-margin-dot" style="background: #557FE6;"></span>
    <span class="ace-margin-note-code">Helpful</span>
  </div>
</div>
```

### CSS Changes (`coding.css`)

- **Scroll wrapper**: new `.ace-content-scroll` with `overflow-y: auto`, internal flex layout
- **Margin panel**: `position: relative; overflow: visible;` (no own scroll)
- **Cards**: `position: absolute;` with JS-set `top`. White background, subtle border, small border-radius, compact padding
- **Code row**: flex row with 8px colour dot + code name
- **Flash animation**: keyframe on `.ace-sentence` elements

```css
@keyframes ace-flash {
  0% { background: rgba(255, 235, 59, 0.7); }
  100% { background: transparent; }
}
.ace-flash {
  animation: ace-flash 1.2s ease-out forwards;
}
```

Note: `animation-fill-mode: forwards` ensures the animation ends at `background: transparent`, which is the default state. The `ace-sentence--focused` class sets its own background — since `ace-flash` is removed after the animation completes (via JS `animationend` listener), the focused background is restored. The flash class must be removed on `animationend`, not via `setTimeout`, to handle this correctly.

### JS Changes (`bridge.js`)

**`_positionMarginCards()`** — batch-reads sentence positions, computes ideal `top` for each card, resolves overlaps, then batch-writes positions:

```javascript
function _positionMarginCards() {
  var wrapper = document.getElementById("content-scroll");
  if (!wrapper) return;
  var cards = Array.from(document.querySelectorAll(".ace-margin-note"));
  if (!cards.length) return;

  var wrapperTop = wrapper.getBoundingClientRect().top;
  var scrollOffset = wrapper.scrollTop;

  // Batch read: compute ideal positions
  var positions = [];
  for (var i = 0; i < cards.length; i++) {
    var startIdx = cards[i].dataset.startIdx;
    var endIdx = cards[i].dataset.endIdx;
    var startEl = document.getElementById("s-" + startIdx);
    var endEl = document.getElementById("s-" + endIdx);
    if (!startEl) continue;
    var startRect = startEl.getBoundingClientRect();
    var endRect = endEl ? endEl.getBoundingClientRect() : startRect;
    var midpoint = (startRect.top + endRect.bottom) / 2 - wrapperTop + scrollOffset;
    positions.push({ card: cards[i], top: midpoint - cards[i].offsetHeight / 2 });
  }

  // Resolve overlaps: single downward pass
  var minGap = 4;
  for (var j = 1; j < positions.length; j++) {
    var prevBottom = positions[j - 1].top + positions[j - 1].card.offsetHeight;
    if (positions[j].top < prevBottom + minGap) {
      positions[j].top = prevBottom + minGap;
    }
  }

  // Batch write
  for (var k = 0; k < positions.length; k++) {
    positions[k].card.style.top = positions[k].top + "px";
  }
}
```

**Triggers:**
- `DOMContentLoaded` — after `_paintHighlights()`
- `htmx:afterSettle` — when `target.id === "text-panel"` or `target.id === "coding-workspace"` (not on `margin-panel` settle — text-panel must be settled first for sentence positions to be correct)
- `ResizeObserver` on the scroll wrapper — catches window resize, sidebar drag-resize, and content reflow

**Click → flash handler:**
```javascript
// In the global click listener, replace _focusSentence with flash
var note = target.closest(".ace-margin-note");
if (note) {
  var start = parseInt(note.dataset.startIdx, 10);
  var end = parseInt(note.dataset.endIdx, 10);
  for (var i = start; i <= end; i++) {
    var s = document.getElementById("s-" + i);
    if (s) {
      s.classList.remove("ace-flash");
      void s.offsetWidth;  // force reflow for re-trigger
      s.classList.add("ace-flash");
      s.addEventListener("animationend", function() {
        this.classList.remove("ace-flash");
      }, { once: true });
    }
  }
  // Scroll first sentence into view
  var first = document.getElementById("s-" + start);
  if (first) first.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
```

### Overlap Grouping

Annotations covering the exact same sentence range merge into one card. For example, if "Used AI" covers sentences 0-1 and "Helpful" also covers sentences 0-1, they share one card with two rows.

Annotations with different ranges get separate cards, even if they overlap partially. For example, "Used AI" on sentences 0-1 and "Helpful" on sentences 1-2 get two separate cards positioned at their respective midpoints.

## Files to Change

| File | Change |
|------|--------|
| `src/ace/services/coding_render.py` | Fix `build_margin_annotations()`: remove `break`, change return type to `codes: list[dict]`, add same-range merge pass, drop `texts` field |
| `src/ace/templates/coding.html` | Add scroll wrapper div, rewrite `margin_panel` block — dot+name cards |
| `src/ace/static/css/coding.css` | Scroll wrapper, margin card absolute positioning, flash animation, remove old margin note styles |
| `src/ace/static/js/bridge.js` | `_positionMarginCards()`, ResizeObserver, click-flash handler (replaces click-focus), update `htmx:afterSettle` |

## What's Removed

- 40-character text preview in margin notes
- "N sentences merged" badge
- Current stacked-list layout (replaced by positioned cards)
- Separate scroll containers for text and margin panels
- `_focusSentence()` call on margin click (replaced by flash)

## What's Preserved

- `build_margin_annotations()` function (modified, not replaced)
- Click interactivity (flash instead of focus)
- Colour indication (dot instead of bar)
- OOB swap mechanism for margin panel updates (JS re-positions after swap)
