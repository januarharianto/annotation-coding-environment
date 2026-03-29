# CSS Custom Highlight API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace DOM-based `<mark>` wrapping with the CSS Custom Highlight API so annotation highlights seamlessly span across sentence-span boundaries.

**Architecture:** Server renders plain sentence `<span>` elements with no highlight markup. Client-side JS reads annotation data from a hidden `<div data-annotations>` element (updated via HTMX OOB swaps), creates `Range` objects that walk text nodes across sentence spans, and registers them via `CSS.highlights.set()`. CSS `::highlight()` pseudo-elements paint the background colours. This cleanly separates navigation (sentence spans) from visualisation (CSS highlights).

**Tech Stack:** CSS Custom Highlight API (Baseline 2025 — Chrome 105+, Safari 17.2+, Firefox 140+), vanilla JS, Jinja2 templates, Python (FastAPI)

**Key constraint:** `::highlight()` only supports `background-color`, `color`, `text-decoration`, `text-shadow`. No box model properties. CSS custom properties (`var()`) inside `::highlight()` are Chrome 134+ only — **must use literal alpha values, not `var(--ace-annotation-alpha)`**.

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `src/ace/services/coding_render.py` | Sentence-span rendering (nav only) | Modify: remove all `<mark>` logic |
| `src/ace/templates/coding.html` | Template: annotation data div + `::highlight()` CSS | Modify |
| `src/ace/static/js/bridge.js` | Highlight manager: Range → CSS highlight | Modify: add section 18 |
| `src/ace/static/css/coding.css` | Remove `mark` styles | Modify |
| `src/ace/routes/api.py` | OOB helpers: include annotation data div | Modify |
| `src/ace/routes/pages.py` | Build `annotation_highlights` list | Modify |
| `tests/test_services/test_coding_render.py` | Unit tests for simplified renderer | Modify |

---

### Task 1: Simplify `render_sentence_text()` — remove all `<mark>` logic

The renderer currently wraps annotations in `<mark>` elements (outer marks for full-sentence, inner marks for partials). Strip all of that — the renderer should only produce sentence `<span>` elements with data attributes and the `ace-sentence--coded` class. Highlights will be painted by JS/CSS instead.

**Files:**
- Modify: `src/ace/services/coding_render.py:80-259`
- Modify: `tests/test_services/test_coding_render.py`

- [ ] **Step 1: Update tests to reflect simplified output**

The tests currently assert `<mark>` elements and `rgba()` inline styles. After this change, the renderer produces no `<mark>` elements — only sentence spans with the `ace-sentence--coded` class when annotations overlap.

Replace the full test file `tests/test_services/test_coding_render.py`:

```python
"""Tests for sentence-based text rendering (no highlight markup)."""

from ace.services.coding_render import render_sentence_text


def test_empty_units():
    assert render_sentence_text([], [], {}) == ""


def test_single_uncoded_sentence():
    units = [{"text": "Hello world.", "type": "prose", "start_offset": 0, "end_offset": 12}]
    html = render_sentence_text(units, [], {})
    assert 'class="ace-sentence"' in html
    assert 'data-idx="0"' in html
    assert "Hello world." in html


def test_coded_sentence_has_coded_class():
    units = [{"text": "Hello.", "type": "prose", "start_offset": 0, "end_offset": 6}]
    annotations = [{"id": "a1", "code_id": "c1", "start_offset": 0, "end_offset": 6}]
    codes_by_id = {"c1": {"id": "c1", "name": "Greeting", "colour": "#e53935"}}
    html = render_sentence_text(units, annotations, codes_by_id)
    assert "ace-sentence--coded" in html
    assert "<mark" not in html


def test_uncoded_sentence_no_coded_class():
    units = [{"text": "Hello.", "type": "prose", "start_offset": 0, "end_offset": 6}]
    html = render_sentence_text(units, [], {})
    assert "ace-sentence--coded" not in html


def test_list_item_class():
    units = [{"text": "- Item one", "type": "list", "start_offset": 0, "end_offset": 10}]
    html = render_sentence_text(units, [], {})
    assert "ace-sentence--list" in html


def test_paragraph_break_between_types():
    units = [
        {"text": "Prose.", "type": "prose", "start_offset": 0, "end_offset": 6},
        {"text": "- List", "type": "list", "start_offset": 8, "end_offset": 14},
    ]
    html = render_sentence_text(units, [], {})
    assert "ace-para-break" in html


def test_paragraph_break_blank_line():
    units = [
        {"text": "First.", "type": "prose", "start_offset": 0, "end_offset": 6},
        {"text": "Second.", "type": "prose", "start_offset": 8, "end_offset": 15},
    ]
    html = render_sentence_text(units, [], {})
    assert "ace-para-break" in html


def test_no_paragraph_break_same_line():
    units = [
        {"text": "First.", "type": "prose", "start_offset": 0, "end_offset": 6},
        {"text": "Second.", "type": "prose", "start_offset": 7, "end_offset": 14},
    ]
    html = render_sentence_text(units, [], {})
    assert "ace-para-break" not in html


def test_sentence_id_attribute():
    units = [{"text": "Hello.", "type": "prose", "start_offset": 0, "end_offset": 6}]
    html = render_sentence_text(units, [], {})
    assert 'id="s-0"' in html


def test_html_escaping():
    units = [{"text": "A < B & C > D", "type": "prose", "start_offset": 0, "end_offset": 13}]
    html = render_sentence_text(units, [], {})
    assert "A &lt; B &amp; C &gt; D" in html


def test_data_start_end_attributes():
    units = [{"text": "Hello.", "type": "prose", "start_offset": 5, "end_offset": 11}]
    html = render_sentence_text(units, [], {})
    assert 'data-start="5"' in html
    assert 'data-end="11"' in html


def test_no_mark_elements_with_annotations():
    """Annotations produce ace-sentence--coded class but no <mark> elements."""
    units = [{"text": "Hello.", "type": "prose", "start_offset": 0, "end_offset": 6}]
    annotations = [
        {"id": "a1", "code_id": "c1", "start_offset": 0, "end_offset": 6},
        {"id": "a2", "code_id": "c2", "start_offset": 0, "end_offset": 6},
    ]
    codes_by_id = {
        "c1": {"id": "c1", "name": "Red", "colour": "#e53935"},
        "c2": {"id": "c2", "name": "Blue", "colour": "#1e88e5"},
    }
    html = render_sentence_text(units, annotations, codes_by_id)
    assert "ace-sentence--coded" in html
    assert "<mark" not in html
    assert "rgba(" not in html


def test_partial_annotation_no_mark():
    """Custom selection within a sentence: no <mark>, just ace-sentence--coded."""
    units = [{"text": "Hello world.", "type": "prose", "start_offset": 0, "end_offset": 12}]
    annotations = [{"id": "a1", "code_id": "c1", "start_offset": 6, "end_offset": 11}]
    codes_by_id = {"c1": {"id": "c1", "name": "Test", "colour": "#43a047"}}
    html = render_sentence_text(units, annotations, codes_by_id)
    assert "ace-sentence--coded" in html
    assert "<mark" not in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_services/test_coding_render.py -v`
Expected: `test_coded_sentence_has_coded_class`, `test_no_mark_elements_with_annotations`, `test_partial_annotation_no_mark` FAIL (current code still produces `<mark>`)

- [ ] **Step 3: Simplify `render_sentence_text()`**

In `src/ace/services/coding_render.py`, replace everything from `render_sentence_text` (line 80) through `_is_para_break` (line 259) with the simplified version below. Delete the now-unused functions: `_get_sentence_annotations`, `_HIGHLIGHT_ALPHA`, `_hex_to_rgba`, `_render_inner_text`, `_wrap_highlight`.

```python
def render_sentence_text(
    units: list[dict],
    annotations: list[dict],
    codes_by_id: dict,
) -> str:
    """Render source text as sentence spans (navigation only).

    Highlights are painted client-side via the CSS Custom Highlight API.
    This function only adds the ``ace-sentence--coded`` class when at
    least one annotation overlaps the sentence.
    """
    if not units:
        return ""

    parts: list[str] = []

    for i, unit in enumerate(units):
        if _is_para_break(i, units):
            parts.append('<span class="ace-para-break"></span>')

        s = unit["start_offset"]
        e = unit["end_offset"]

        classes = ["ace-sentence"]
        if unit["type"] == "list":
            classes.append("ace-sentence--list")
        if _has_overlap(s, e, annotations):
            classes.append("ace-sentence--coded")

        cls = " ".join(classes)
        inner = html.escape(unit["text"])
        parts.append(
            f'<span id="s-{i}" class="{cls}" data-idx="{i}" '
            f'data-start="{s}" data-end="{e}">{inner}</span> '
        )

    return "".join(parts)


def _has_overlap(start: int, end: int, annotations: list[dict]) -> bool:
    """Check if any annotation overlaps [start, end)."""
    for ann in annotations:
        if ann["start_offset"] < end and ann["end_offset"] > start:
            return True
    return False


def _is_para_break(idx: int, units: list[dict]) -> bool:
    """Check if there should be a paragraph break before unit at idx."""
    if idx == 0:
        return False
    prev = units[idx - 1]
    curr = units[idx]
    if prev["type"] != curr["type"]:
        return True
    if curr["start_offset"] - prev["end_offset"] > 1:
        return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_services/test_coding_render.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest`
Expected: All 237+ tests PASS. If any test imports `_hex_to_rgba` or similar removed helpers, update those tests.

- [ ] **Step 6: Commit**

```bash
git add src/ace/services/coding_render.py tests/test_services/test_coding_render.py
git commit -m "refactor: strip mark wrapping from render_sentence_text (CSS Highlight API prep)"
```

---

### Task 2: Pass annotation data to client via hidden DOM element

The CSS Highlight API is driven by JavaScript. The client needs annotation data (offsets + colours). We use a hidden `<div data-annotations='...'>` element instead of a `<script>` tag — this avoids browser script-execution timing issues with HTMX OOB swaps.

**Files:**
- Modify: `src/ace/routes/pages.py` — build `annotation_highlights` list
- Modify: `src/ace/templates/coding.html` — add data div + `__aceAnnotations` init
- Modify: `src/ace/routes/api.py` — update all three OOB helpers

- [ ] **Step 1: Build `annotation_highlights` in `_coding_context()`**

In `src/ace/routes/pages.py`, after the `code_counts` loop (after line 151, the blank line following `code_counts[cid] = code_counts.get(cid, 0) + 1`), add:

```python
    # Annotation data for CSS Highlight API (client-side rendering)
    annotation_highlights = []
    for ann in annotations_list:
        code = codes_by_id.get(ann["code_id"])
        if code:
            annotation_highlights.append({
                "id": ann["id"],
                "code_id": ann["code_id"],
                "start": ann["start_offset"],
                "end": ann["end_offset"],
                "colour": code["colour"],
            })
```

And add `"annotation_highlights": annotation_highlights,` to the return dict (after `"margin_annotations"`).

- [ ] **Step 2: Add the data div to `coding.html`**

In `src/ace/templates/coding.html`, inside `#coding-workspace`, just before the `{# Modal container #}` comment (line 193), add:

```html
  {# Annotation data for CSS Highlight API (updated via OOB swap) #}
  <div id="ace-ann-data" class="ace-hidden"
       data-annotations="{{ annotation_highlights | tojson | e }}"></div>
```

Note: `| e` escapes the JSON for safe embedding in an HTML attribute (double quotes → `&quot;`).

- [ ] **Step 3: Add `_render_ann_data_oob()` helper to `api.py`**

Add a new helper function near the other OOB helpers in `api.py` (after `_render_colour_style_oob`, around line 511). `html` is already imported at the top of `api.py`:

```python
def _render_ann_data_oob(ctx: dict) -> str:
    """Generate OOB div with annotation data for CSS Highlight API."""
    ann_json = html.escape(json.dumps(ctx.get("annotation_highlights", [])))
    return f'<div id="ace-ann-data" class="ace-hidden" data-annotations="{ann_json}" hx-swap-oob="outerHTML"></div>'
```

This uses `html.escape()` with double-quoted attributes — safe against all character content (matching the template's `| tojson | e` approach).

- [ ] **Step 4: Update `_render_coding_oob()` in `api.py`**

In `src/ace/routes/api.py`, modify `_render_coding_oob()` (line 513). Append the annotation data OOB div to the return:

```python
def _render_coding_oob(request: Request, conn, coder_id: str, current_index: int) -> str:
    """Render text_panel (primary) + margin_panel + annotation data (OOB)."""
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    ctx = _coding_context(conn, coder_id, current_index)
    ctx["request"] = request

    text_html = render_block(templates.env, "coding.html", "text_panel", ctx)
    margin_html = render_block(templates.env, "coding.html", "margin_panel", ctx)

    return text_html + _inject_oob(margin_html, "margin-panel") + _render_ann_data_oob(ctx)
```

- [ ] **Step 5: Update `_render_full_coding_oob()` in `api.py`**

In `src/ace/routes/api.py`, modify `_render_full_coding_oob()` (line 527). After `parts.append(_render_colour_style_oob(ctx["codes"]))` (line 550), add:

```python
    parts.append(_render_ann_data_oob(ctx))
```

- [ ] **Step 6: Update `_render_sidebar_and_text()` in `api.py`**

In `src/ace/routes/api.py`, modify `_render_sidebar_and_text()` (line 998). After `+ _render_colour_style_oob(ctx["codes"])` (line 1015), add `+ _render_ann_data_oob(ctx)`:

```python
    return (
        sidebar_html
        + _inject_oob(text_html, "text-panel")
        + _inject_oob(margin_html, "margin-panel")
        + _render_colour_style_oob(ctx["codes"])
        + _render_ann_data_oob(ctx)
    )
```

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/ace/routes/pages.py src/ace/templates/coding.html src/ace/routes/api.py
git commit -m "feat: pass annotation data to client via hidden DOM element"
```

---

### Task 3: Implement the JS highlight manager

Add functions to `bridge.js` that:
1. Read annotation data from `#ace-ann-data` DOM element
2. For each annotation, create a `Range` spanning from `start` to `end` by walking text nodes in `#text-panel`
3. Group ranges by `code_id` (each code gets one `Highlight` object)
4. Register via `CSS.highlights.set("ace-hl-{code_id}", highlight)`
5. Run on DOMContentLoaded and after every HTMX swap of `#text-panel` or `#coding-workspace`

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Add the highlight manager functions as section 18**

In `src/ace/static/js/bridge.js`, before the section 17 `DOMContentLoaded init` block (before line 1253), add a new section:

```javascript
  /* ================================================================
   * 18. CSS Custom Highlight API — annotation rendering
   * ================================================================ */

  /**
   * Build a flat list of {node, sourceStart, sourceEnd} entries
   * for all text nodes inside sentence spans in the text panel.
   */
  function _buildTextIndex(container) {
    var index = [];
    var walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
    var node;
    while ((node = walker.nextNode())) {
      var sentence = node.parentElement.closest(".ace-sentence");
      if (!sentence) continue;
      var sentStart = parseInt(sentence.dataset.start, 10);
      if (isNaN(sentStart)) continue;

      // Count characters in text nodes before this one within the sentence
      var charsBefore = 0;
      var tw = document.createTreeWalker(sentence, NodeFilter.SHOW_TEXT, null);
      var t;
      while ((t = tw.nextNode())) {
        if (t === node) break;
        charsBefore += t.textContent.length;
      }

      var nodeSourceStart = sentStart + charsBefore;
      index.push({
        node: node,
        sourceStart: nodeSourceStart,
        sourceEnd: nodeSourceStart + node.textContent.length,
      });
    }
    return index;
  }

  /**
   * Find the DOM position (node + offset) for a source character offset.
   */
  function _findDOMPosition(textIndex, sourceOffset) {
    for (var i = 0; i < textIndex.length; i++) {
      var entry = textIndex[i];
      if (sourceOffset >= entry.sourceStart && sourceOffset <= entry.sourceEnd) {
        return { node: entry.node, offset: sourceOffset - entry.sourceStart };
      }
    }
    return null;
  }

  /**
   * Paint all annotation highlights using the CSS Custom Highlight API.
   * Reads annotation data from the hidden #ace-ann-data element,
   * groups by code_id, and registers CSS highlights.
   */
  function _paintHighlights() {
    if (!CSS.highlights) return;  // API not supported
    CSS.highlights.clear();

    // Read annotation data from DOM element (updated by OOB swaps)
    var dataEl = document.getElementById("ace-ann-data");
    if (!dataEl) return;
    var annotations = JSON.parse(dataEl.dataset.annotations || "[]");
    if (!annotations.length) return;

    var container = document.getElementById("text-panel");
    if (!container) return;

    var textIndex = _buildTextIndex(container);
    if (!textIndex.length) return;

    // Group ranges by code_id
    var groups = {};
    for (var i = 0; i < annotations.length; i++) {
      var ann = annotations[i];
      var startPos = _findDOMPosition(textIndex, ann.start);
      var endPos = _findDOMPosition(textIndex, ann.end);
      if (!startPos || !endPos) continue;

      try {
        var range = new Range();
        range.setStart(startPos.node, startPos.offset);
        range.setEnd(endPos.node, endPos.offset);

        var codeId = ann.code_id;
        if (!groups[codeId]) groups[codeId] = [];
        groups[codeId].push(range);
      } catch (e) {
        // Invalid range (e.g. end before start) — skip
      }
    }

    // Register highlights
    for (var codeId in groups) {
      if (!groups.hasOwnProperty(codeId)) continue;
      var highlight = new Highlight();
      for (var j = 0; j < groups[codeId].length; j++) {
        highlight.add(groups[codeId][j]);
      }
      CSS.highlights.set("ace-hl-" + codeId, highlight);
    }
  }
```

- [ ] **Step 2: Add `_paintHighlights()` to existing `htmx:afterSettle` handler**

In bridge.js, find the existing `htmx:afterSettle` listener (line 735). Add `_paintHighlights()` to the text-panel/coding-workspace branch. The handler already checks for both target IDs:

```javascript
  document.addEventListener("htmx:afterSettle", function (evt) {
    var target = evt.detail.target;
    if (!target) return;

    if (target.id === "text-panel" || target.id === "coding-workspace") {
      _restoreFocus();
      _paintHighlights();  // <-- ADD THIS LINE
    }

    if (target.id === "code-sidebar" || target.id === "coding-workspace") {
      _buildTabContent("recent");
      _buildTabContent("all");
      _updateKeycaps();
      if (!_isDragging) _initSortable();
    }

    // Auto-open dialogs
    if (target.id === "modal-container") {
      var dialog = target.querySelector("dialog");
      if (dialog && !dialog.open) dialog.showModal();
    }
  });
```

- [ ] **Step 3: Add `_paintHighlights()` to `DOMContentLoaded` handler**

In section 17 (line 1257), add `_paintHighlights()` after `_initSortable()`:

```javascript
  document.addEventListener("DOMContentLoaded", function () {
    _initResize();
    _buildTabContent("recent");
    _buildTabContent("all");
    _updateKeycaps();
    _initSortable();
    _paintHighlights();  // <-- ADD THIS LINE

    // Auto-focus first sentence so keyboard works immediately
    var sentences = _getSentences();
    if (sentences.length > 0) {
      _focusSentence(0);
    }
    var tp = document.getElementById("text-panel");
    if (tp) tp.focus();
  });
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ace/static/js/bridge.js
git commit -m "feat: CSS Custom Highlight API — paint annotations via JS ranges"
```

---

### Task 4: CSS `::highlight()` rules

Replace the existing `<mark>` styles with `::highlight()` pseudo-element rules. Each code's highlight is named `ace-hl-{code_id}`.

**Critical:** `::highlight()` does NOT support CSS custom properties (`var()`) cross-browser — only Chrome 134+. Use a literal alpha value (`0.3`) instead of `var(--ace-annotation-alpha)`.

**Files:**
- Modify: `src/ace/static/css/coding.css:387-390`
- Modify: `src/ace/templates/coding.html:16-22`
- Modify: `src/ace/routes/api.py` (`_render_colour_style_oob`)

- [ ] **Step 1: Remove the `<mark>` styles from coding.css**

In `src/ace/static/css/coding.css`, delete the `.ace-sentence mark` rule block (lines 387–390):

```css
/* DELETE THIS: */
.ace-sentence mark {
  color: inherit;
  padding: 1px 0;
}
```

- [ ] **Step 2: Add `::highlight()` rules to the `<style id="code-colours">` block**

In `src/ace/templates/coding.html`, update the `<style id="code-colours">` block to generate `::highlight()` rules alongside the existing `.ace-code-{id}` classes. Use literal `0.3` for the highlight alpha:

```html
<style id="code-colours">
{% for code in codes %}
.ace-code-{{ code["id"] }} {
  background-color: rgba({{ code["colour"][1:3] | int(base=16) }}, {{ code["colour"][3:5] | int(base=16) }}, {{ code["colour"][5:7] | int(base=16) }}, var(--ace-annotation-alpha));
}
::highlight(ace-hl-{{ code["id"] }}) {
  background-color: rgba({{ code["colour"][1:3] | int(base=16) }}, {{ code["colour"][3:5] | int(base=16) }}, {{ code["colour"][5:7] | int(base=16) }}, 0.3);
}
{% endfor %}
</style>
```

- [ ] **Step 3: Update `_render_colour_style_oob()` in `api.py`**

In `src/ace/routes/api.py`, update `_render_colour_style_oob()` (line 505) to include `::highlight()` rules. Reuse the existing `_hex_to_rgb()` helper. Use literal `0.3` for the highlight alpha:

```python
def _render_colour_style_oob(codes: list[dict]) -> str:
    """Generate <style> block with per-code CSS classes and ::highlight() rules."""
    parts = []
    for code in codes:
        r, g, b = _hex_to_rgb(code["colour"])
        cid = code["id"]
        parts.append(
            f".ace-code-{cid} {{"
            f" background-color: rgba({r},{g},{b},var(--ace-annotation-alpha)); }}"
        )
        parts.append(
            f"::highlight(ace-hl-{cid}) {{"
            f" background-color: rgba({r},{g},{b},0.3); }}"
        )
    return f'<style id="code-colours" hx-swap-oob="outerHTML">{chr(10).join(parts)}</style>'
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ace/static/css/coding.css src/ace/templates/coding.html src/ace/routes/api.py
git commit -m "feat: ::highlight() CSS rules for annotation colours"
```

---

### Task 5: Clean up dead code

After tasks 1–4, several Python functions are unused. Remove them.

**Files:**
- Modify: `src/ace/services/coding_render.py`
- Modify: `tests/test_coding_render.py`

- [ ] **Step 1: Check if `render_annotated_text()` is used in production code**

Run: `grep -rn "render_annotated_text" src/ace/`

Expected: No matches (it's only used in `tests/test_coding_render.py`). If confirmed unused in production, remove `render_annotated_text()` and its helper `_annotation_span()` from `coding_render.py`, and remove `tests/test_coding_render.py` (the root-level one, NOT `tests/test_services/test_coding_render.py`).

- [ ] **Step 2: Verify all mark-wrapping helpers were removed in Task 1**

In `src/ace/services/coding_render.py`, confirm these are gone:
- `_get_sentence_annotations()`
- `_HIGHLIGHT_ALPHA`
- `_hex_to_rgba()`
- `_render_inner_text()`
- `_wrap_highlight()`

If any remain, delete them.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All PASS (test count will drop by ~5 from removing `tests/test_coding_render.py`)

- [ ] **Step 4: Commit**

```bash
git add src/ace/services/coding_render.py tests/
git commit -m "refactor: remove dead render_annotated_text and mark-wrapping helpers"
```

---

### Task 6: Visual verification and fix-up

This task cannot be TDD'd — it's a visual check using the running app and agent-browser.

**Files:** Any files from Tasks 1–5 that need adjustment.

- [ ] **Step 1: Start the dev server**

Run: `uv run uvicorn ace.app:create_app --factory --host 127.0.0.1 --port 8080 --reload --reload-dir src/ace`

- [ ] **Step 2: Verify highlights render correctly**

Open `http://127.0.0.1:8080/code` in agent-browser. Test:

1. **Single-sentence annotation**: Press a hotkey on a focused sentence → highlight appears
2. **Cross-sentence annotation**: Drag-select across 2+ sentences, press hotkey → seamless highlight with no gap at sentence boundaries
3. **Multiple codes on same sentence**: Apply two different codes → both visible (one wins per region, controlled by registration order)
4. **Navigate away and back**: Arrow left/right → highlights repaint correctly on new source
5. **Undo/redo**: Press Z → highlight removed, press Z again → highlight restored
6. **Partial annotation within sentence**: Drag-select part of a sentence → only selected text highlighted

- [ ] **Step 3: Fix any visual issues found**

Common issues to watch for:
- Highlights not appearing → check `_paintHighlights()` is called, check `CSS.highlights` exists, check `#ace-ann-data` has data
- Highlights misaligned → check `_buildTextIndex` offset calculation
- Colours wrong → check `::highlight()` rules match code IDs, check literal alpha value
- Safari: check elements don't have `user-select: none` (confirmed safe, but double-check)

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: visual adjustments for CSS Highlight API rendering"
```

(Skip this commit if no fixes needed.)
