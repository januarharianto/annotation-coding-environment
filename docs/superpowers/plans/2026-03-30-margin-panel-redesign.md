# Margin Panel Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stacked-list margin panel with positionally-aligned floating cards that show code names aligned vertically to their coded text, with overlap grouping and click-to-flash.

**Architecture:** Server builds margin groups with multi-code support. Template renders absolutely-positioned cards. JS computes vertical positions from sentence elements, resolves overlaps, and handles click-to-flash. Text panel and margin panel share a single scroll container.

**Tech Stack:** Python (FastAPI), Jinja2 templates, vanilla JS, CSS

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `src/ace/services/coding_render.py` | `build_margin_annotations()` — multi-sentence, multi-code grouping | Modify |
| `tests/test_services/test_coding_render.py` | Tests for `build_margin_annotations()` | Modify (add tests) |
| `src/ace/templates/coding.html` | Scroll wrapper + margin card template | Modify |
| `src/ace/static/css/coding.css` | Scroll wrapper, card positioning, flash animation | Modify |
| `src/ace/static/js/bridge.js` | `_positionMarginCards()`, ResizeObserver, click-flash | Modify |

---

### Task 1: Rewrite `build_margin_annotations()` with TDD

Fix cross-sentence mapping (remove `break`), change return type to support multiple codes per group, add same-range merge pass, drop `texts` field.

**Files:**
- Modify: `src/ace/services/coding_render.py:66-115`
- Modify: `tests/test_services/test_coding_render.py`

- [ ] **Step 1: Write tests for the new behaviour**

Append these tests to `tests/test_services/test_coding_render.py`:

```python
from ace.services.coding_render import build_margin_annotations


# --- build_margin_annotations tests ---

def _units(*ranges):
    """Helper: create unit dicts from (start, end) tuples."""
    return [
        {"text": f"S{i}", "type": "prose", "start_offset": s, "end_offset": e}
        for i, (s, e) in enumerate(ranges)
    ]


def _ann(ann_id, code_id, start, end):
    """Helper: create annotation dict."""
    return {"id": ann_id, "code_id": code_id, "start_offset": start, "end_offset": end}


_CODES = {
    "c1": {"id": "c1", "name": "Red", "colour": "#e53935"},
    "c2": {"id": "c2", "name": "Blue", "colour": "#1e88e5"},
    "c3": {"id": "c3", "name": "Green", "colour": "#43a047"},
}


def test_margin_empty():
    assert build_margin_annotations([], [], {}) == []
    assert build_margin_annotations(_units((0, 5)), [], _CODES) == []


def test_margin_single_annotation():
    units = _units((0, 10), (11, 20))
    anns = [_ann("a1", "c1", 0, 10)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 1
    assert result[0]["start_idx"] == 0
    assert result[0]["end_idx"] == 0
    assert len(result[0]["codes"]) == 1
    assert result[0]["codes"][0]["code_id"] == "c1"
    assert result[0]["codes"][0]["code_name"] == "Red"
    assert result[0]["codes"][0]["colour"] == "#e53935"


def test_margin_adjacent_same_code_merges():
    units = _units((0, 10), (11, 20), (21, 30))
    anns = [_ann("a1", "c1", 0, 10), _ann("a2", "c1", 11, 20)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 1
    assert result[0]["start_idx"] == 0
    assert result[0]["end_idx"] == 1


def test_margin_adjacent_different_codes_separate():
    units = _units((0, 10), (11, 20))
    anns = [_ann("a1", "c1", 0, 10), _ann("a2", "c2", 11, 20)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 2


def test_margin_same_range_overlap_grouped():
    """Two different codes on the same sentence merge into one group."""
    units = _units((0, 10), (11, 20))
    anns = [_ann("a1", "c1", 0, 10), _ann("a2", "c2", 0, 10)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 1
    assert result[0]["start_idx"] == 0
    assert result[0]["end_idx"] == 0
    assert len(result[0]["codes"]) == 2
    code_ids = {c["code_id"] for c in result[0]["codes"]}
    assert code_ids == {"c1", "c2"}


def test_margin_partial_overlap_separate():
    """Different ranges get separate groups even if they overlap."""
    units = _units((0, 10), (11, 20), (21, 30))
    anns = [_ann("a1", "c1", 0, 20), _ann("a2", "c2", 11, 30)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 2
    assert result[0]["start_idx"] == 0
    assert result[1]["start_idx"] == 1


def test_margin_cross_sentence_annotation():
    """A single annotation spanning 3 sentences maps to all of them."""
    units = _units((0, 10), (11, 20), (21, 30))
    anns = [_ann("a1", "c1", 0, 30)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 1
    assert result[0]["start_idx"] == 0
    assert result[0]["end_idx"] == 2


def test_margin_gap_no_merge():
    """Same code on non-adjacent sentences stays separate."""
    units = _units((0, 10), (11, 20), (21, 30))
    anns = [_ann("a1", "c1", 0, 10), _ann("a2", "c1", 21, 30)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 2


def test_margin_unknown_code_skipped():
    units = _units((0, 10))
    anns = [_ann("a1", "unknown", 0, 10)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 0


def test_margin_no_texts_field():
    """New return type has no 'texts' field."""
    units = _units((0, 10))
    anns = [_ann("a1", "c1", 0, 10)]
    result = build_margin_annotations(units, anns, _CODES)
    assert "texts" not in result[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_services/test_coding_render.py -v -k margin`
Expected: Most tests FAIL (old function returns different shape)

- [ ] **Step 3: Rewrite `build_margin_annotations()`**

Replace the function in `src/ace/services/coding_render.py` (lines 66–115) with:

```python
def build_margin_annotations(
    units: list[dict],
    annotations: list[dict],
    codes_by_id: dict,
) -> list[dict]:
    """Build annotation groups for the right margin panel.

    Maps each annotation to ALL overlapping sentence indices, merges
    adjacent same-code annotations, then groups annotations that cover
    the exact same sentence range into a single entry with multiple codes.

    Returns list of dicts with keys: codes (list), start_idx, end_idx.
    """
    if not units or not annotations:
        return []

    # Map each annotation to all overlapping sentence indices
    ann_sentences: list[tuple[int, int, dict]] = []
    for ann in annotations:
        code = codes_by_id.get(ann["code_id"])
        if not code:
            continue
        first_idx = None
        last_idx = None
        for i, unit in enumerate(units):
            if ann["start_offset"] < unit["end_offset"] and ann["end_offset"] > unit["start_offset"]:
                if first_idx is None:
                    first_idx = i
                last_idx = i
        if first_idx is not None:
            ann_sentences.append((first_idx, last_idx, ann))

    # Sort by start index, then end index
    ann_sentences.sort(key=lambda x: (x[0], x[1]))

    # Group adjacent same-code annotations
    groups: list[dict] = []
    for first_idx, last_idx, ann in ann_sentences:
        code = codes_by_id[ann["code_id"]]
        if (
            groups
            and len(groups[-1]["codes"]) == 1
            and groups[-1]["codes"][0]["code_id"] == ann["code_id"]
            and groups[-1]["end_idx"] >= first_idx - 1
        ):
            groups[-1]["end_idx"] = max(groups[-1]["end_idx"], last_idx)
        else:
            groups.append({
                "codes": [{"code_id": ann["code_id"], "code_name": code["name"], "colour": code["colour"]}],
                "start_idx": first_idx,
                "end_idx": last_idx,
            })

    # Merge groups with identical (start_idx, end_idx) ranges
    merged: list[dict] = []
    for group in groups:
        key = (group["start_idx"], group["end_idx"])
        if merged and (merged[-1]["start_idx"], merged[-1]["end_idx"]) == key:
            # Add codes that aren't already present
            existing_ids = {c["code_id"] for c in merged[-1]["codes"]}
            for c in group["codes"]:
                if c["code_id"] not in existing_ids:
                    merged[-1]["codes"].append(c)
                    existing_ids.add(c["code_id"])
        else:
            merged.append(group)

    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_services/test_coding_render.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest`
Expected: All 232 tests PASS

- [ ] **Step 6: Do NOT commit yet** — Task 2 changes the template to match the new return type. Committing Task 1 alone would crash the app (template accesses old fields like `group['colour']`). Continue to Task 2 and commit both together.

---

### Task 2: Scroll wrapper + template + CSS

Add the shared scroll container, rewrite the margin panel template, and update CSS. **This task must be committed together with Task 1** — the data shape change and template change are atomic.

**Files:**
- Modify: `src/ace/templates/coding.html:128-163`
- Modify: `src/ace/static/css/coding.css:130-138, 344-455`

- [ ] **Step 1: Add scroll wrapper to template**

In `src/ace/templates/coding.html`, wrap the text panel and margin panel blocks in a scroll wrapper div. Replace lines 128–163 (from the resize handle through the end of `</div>` closing `ace-three-col`):

Find this section:
```html
    {# Resize handle #}
    <div class="ace-resize-handle" id="resize-handle"></div>

    {# Centre: text panel #}
    {% block text_panel %}
    ...
    {% endblock %}

    {# Right: margin annotations #}
    {% block margin_panel %}
    ...
    {% endblock %}

  </div>
```

Replace with:
```html
    {# Resize handle #}
    <div class="ace-resize-handle" id="resize-handle"></div>

    {# Shared scroll container for text + margin #}
    <div id="content-scroll" class="ace-content-scroll">

      {# Centre: text panel #}
      {% block text_panel %}
      <div id="text-panel" class="ace-text-panel" tabindex="0">
        {% if sentence_html %}
        {{ sentence_html | safe }}
        {% elif source_text %}
        <p>{{ source_text }}</p>
        {% else %}
        <p class="ace-text-empty">No source content.</p>
        {% endif %}
      </div>
      {% endblock %}

      {# Right: margin annotations #}
      {% block margin_panel %}
      <div id="margin-panel" class="ace-margin-panel">
        {% for group in margin_annotations %}
        <div class="ace-margin-note" data-start-idx="{{ group['start_idx'] }}" data-end-idx="{{ group['end_idx'] }}">
          {% for code in group['codes'] %}
          <div class="ace-margin-note-row">
            <span class="ace-margin-dot" style="background: {{ code['colour'] }};"></span>
            <span class="ace-margin-note-code">{{ code['code_name'] }}</span>
          </div>
          {% endfor %}
        </div>
        {% endfor %}
        {% if not margin_annotations %}
        <div class="ace-margin-empty">No annotations yet</div>
        {% endif %}
      </div>
      {% endblock %}

    </div>

  </div>
```

- [ ] **Step 2: Update CSS — grid, scroll wrapper, margin styles**

In `src/ace/static/css/coding.css`, make these changes:

**2a. Update grid to 3 columns** (line 134):
```css
/* Change from: */
grid-template-columns: var(--ace-sidebar-width) 1px 1fr 200px;
/* To: */
grid-template-columns: var(--ace-sidebar-width) 1px 1fr;
```

**2b. Update text panel** — remove `overflow-y: auto` (scroll handled by wrapper now). Replace lines 346–352:
```css
.ace-text-panel {
  flex: 1;
  padding: var(--ace-space-6) var(--ace-space-8);
  outline: none;
  line-height: 2;
  font-size: var(--ace-font-size-base);
}
```

**2c. Add scroll wrapper** — insert after `.ace-text-empty` rule (after line 362):
```css
/* ---- Content scroll wrapper ---- */

.ace-content-scroll {
  display: flex;
  overflow-y: auto;
  min-height: 0;
}
```

**2d. Replace margin panel styles** — replace lines 395–455 (all `.ace-margin-*` rules) with:
```css
/* ---- Right margin panel ---- */

.ace-margin-panel {
  width: 180px;
  flex-shrink: 0;
  position: relative;
  border-left: 1px solid var(--ace-border);
}

.ace-margin-note {
  position: absolute;
  left: 0;
  right: 0;
  padding: 4px 8px;
  background: var(--ace-bg);
  border: 1px solid var(--ace-border-light);
  border-radius: var(--ace-radius);
  font-size: var(--ace-font-size-xs);
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
  transition: box-shadow var(--ace-transition);
}

.ace-margin-note:hover {
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
}

.ace-margin-note-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 1px 0;
}

.ace-margin-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ace-margin-note-code {
  font-weight: var(--ace-weight-medium);
  color: var(--ace-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ace-margin-empty {
  padding: var(--ace-space-4);
  color: var(--ace-text-muted);
  font-size: var(--ace-font-size-sm);
  text-align: center;
  position: absolute;
  top: var(--ace-space-4);
  left: 0;
  right: 0;
}

/* ---- Flash animation ---- */

@keyframes ace-flash {
  0% { background: rgba(255, 235, 59, 0.7); }
  100% { background: transparent; }
}

.ace-flash {
  animation: ace-flash 1.2s ease-out;
}
```

**2e. Update resize handler hardcoded column** — this is done in Task 3 (JS), not here.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/ace/services/coding_render.py tests/test_services/test_coding_render.py src/ace/templates/coding.html src/ace/static/css/coding.css
git commit -m "feat: margin panel redesign — positioned cards with overlap grouping"
```

---

### Task 3: JS — positioning, click-flash, ResizeObserver

Add `_positionMarginCards()`, update click handler to flash instead of focus, add ResizeObserver, update resize handler and afterSettle.

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Add `_positionMarginCards()` as section 19**

Insert before the section 17 `DOMContentLoaded init` block (before line 1364). Note: section 18 is the CSS Custom Highlight API section.

```javascript
  /* ================================================================
   * 19. Margin card positioning
   * ================================================================ */

  function _positionMarginCards() {
    var wrapper = document.getElementById("content-scroll");
    if (!wrapper) return;
    var textPanel = document.getElementById("text-panel");
    var marginPanel = document.getElementById("margin-panel");
    if (!textPanel || !marginPanel) return;

    // Sync margin panel height to text panel content height
    // (absolute children don't contribute height in flex layout)
    marginPanel.style.minHeight = textPanel.scrollHeight + "px";

    var cards = Array.from(document.querySelectorAll(".ace-margin-note"));
    if (!cards.length) return;

    var wrapperRect = wrapper.getBoundingClientRect();
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
      var midpoint = (startRect.top + endRect.bottom) / 2 - wrapperRect.top + scrollOffset;
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

  // Schedule positioning via rAF to batch layout operations
  var _positionRafPending = false;
  function _schedulePosition() {
    if (_positionRafPending) return;
    _positionRafPending = true;
    requestAnimationFrame(function () {
      _positionRafPending = false;
      _positionMarginCards();
    });
  }
```

- [ ] **Step 2: Replace margin click handler with flash**

In bridge.js, find the margin note click handler (around line 723-728):
```javascript
    // Click on margin note to highlight corresponding sentences
    var note = e.target.closest(".ace-margin-note");
    if (note) {
      var startIdx = parseInt(note.dataset.startIdx, 10);
      if (!isNaN(startIdx)) _focusSentence(startIdx);
    }
```

Replace with:
```javascript
    // Click on margin note to flash corresponding sentences
    var note = e.target.closest(".ace-margin-note");
    if (note) {
      var flashStart = parseInt(note.dataset.startIdx, 10);
      var flashEnd = parseInt(note.dataset.endIdx, 10);
      if (!isNaN(flashStart)) {
        for (var fi = flashStart; fi <= flashEnd; fi++) {
          var fs = document.getElementById("s-" + fi);
          if (fs) {
            fs.classList.remove("ace-flash");
            void fs.offsetWidth;
            fs.classList.add("ace-flash");
            fs.addEventListener("animationend", function () {
              this.classList.remove("ace-flash");
            }, { once: true });
          }
        }
        var firstFlash = document.getElementById("s-" + flashStart);
        if (firstFlash) firstFlash.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
```

- [ ] **Step 3: Add `_positionMarginCards()` to afterSettle handler**

In the existing `htmx:afterSettle` handler (around line 737-740), add `_schedulePosition()` after `_paintHighlights()`:

```javascript
    if (target.id === "text-panel" || target.id === "coding-workspace") {
      _restoreFocus();
      _paintHighlights();
      _schedulePosition();
    }
```

- [ ] **Step 4: Add ResizeObserver and update DOMContentLoaded**

In the DOMContentLoaded handler, add `_positionMarginCards()` after `_paintHighlights()` and set up a ResizeObserver:

```javascript
  document.addEventListener("DOMContentLoaded", function () {
    _initResize();
    _buildTabContent("recent");
    _buildTabContent("all");
    _updateKeycaps();
    _initSortable();
    _paintHighlights();
    _positionMarginCards();

    // Auto-focus first sentence so keyboard works immediately
    var sentences = _getSentences();
    if (sentences.length > 0) {
      _focusSentence(0);
    }
    var tp = document.getElementById("text-panel");
    if (tp) tp.focus();

    // Re-position margin cards on container resize
    var scrollWrapper = document.getElementById("content-scroll");
    if (scrollWrapper && typeof ResizeObserver !== "undefined") {
      new ResizeObserver(_schedulePosition).observe(scrollWrapper);
    }
  });
```

- [ ] **Step 5: Update resize handler grid columns**

In `_initResize()`, update the hardcoded grid column strings. Find the two occurrences of `"px 1px 1fr 200px"` (around lines 604 and 624) and replace with `"px 1px 1fr"`:

Line ~604:
```javascript
// Change from:
split.style.gridTemplateColumns = saved + "px 1px 1fr 200px";
// To:
split.style.gridTemplateColumns = saved + "px 1px 1fr";
```

Line ~624:
```javascript
// Change from:
split.style.gridTemplateColumns = x + "px 1px 1fr 200px";
// To:
split.style.gridTemplateColumns = x + "px 1px 1fr";
```

Also add `_schedulePosition()` to the `pointerup` handler (line ~627) so margin cards reposition after sidebar drag-resize:

After `dragging = false;` in the pointerup handler, add:
```javascript
      _schedulePosition();
```

- [ ] **Step 6: Reset scroll on source navigation**

In the `ace-navigate` event handler (around line 770-781), add scroll reset so the shared scroll container doesn't retain the previous source's position:

```javascript
  document.addEventListener("ace-navigate", function (e) {
    var detail = e.detail || {};
    if (detail.index !== undefined) {
      window.__aceCurrentIndex = parseInt(detail.index, 10);
    }
    if (detail.total !== undefined) {
      window.__aceTotalSources = parseInt(detail.total, 10);
    }
    window.__aceFocusIndex = -1;
    var input = document.getElementById("current-index");
    if (input) input.value = window.__aceCurrentIndex;
    // Reset scroll position for new source
    var cs = document.getElementById("content-scroll");
    if (cs) cs.scrollTop = 0;
  });
```

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/ace/static/js/bridge.js
git commit -m "feat: margin card positioning, click-flash, and ResizeObserver"
```

---

### Task 4: Visual verification

This task cannot be TDD'd — it's a visual check using the running app.

**Files:** Any files from Tasks 1–3 that need adjustment.

- [ ] **Step 1: Start the dev server**

Run: `uv run uvicorn ace.app:create_app --factory --host 127.0.0.1 --port 8080 --reload --reload-dir src/ace`

- [ ] **Step 2: Verify margin cards**

Open `http://127.0.0.1:8080/code` in a browser. Test:

1. **Card positioning**: margin cards should align vertically with their coded sentences
2. **Overlap grouping**: two codes on the same sentence should show as one card with two dot+name rows
3. **Click-flash**: clicking a margin card should flash the coded sentences yellow (~1.2s), without changing keyboard focus
4. **Scroll sync**: scrolling the text panel should scroll the margin cards in sync (shared container)
5. **Apply new code**: press a hotkey on a focused sentence → margin card appears at the right position
6. **Undo**: press Z → margin card disappears
7. **Navigate sources**: Shift+arrow → margin cards update for the new source
8. **Resize sidebar**: drag the sidebar handle → margin cards reposition
9. **Anti-collision**: code two adjacent sentences with different codes → cards should not overlap

- [ ] **Step 3: Fix any visual issues found**

Common issues:
- Cards not appearing → check `_positionMarginCards()` is called, check `#content-scroll` exists
- Cards at wrong position → check `getBoundingClientRect` calculation, verify scroll wrapper
- Cards overlapping → check overlap resolution pass
- Flash not working → check `ace-flash` CSS class, animation keyframes
- Text panel not scrollable → check `.ace-content-scroll` has `overflow-y: auto`

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: visual adjustments for margin panel redesign"
```

(Skip this commit if no fixes needed.)
