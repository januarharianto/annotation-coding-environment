# Bottom Code Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the right margin panel with a sticky bottom code bar showing clickable code chips that flash their sentences in the code's own colour.

**Architecture:** Delete the margin panel (template block, CSS, JS positioning, OOB helpers). Add a sticky bar inside the text panel with code chips. Chip click reads annotation data from `#ace-ann-data` and flashes matching sentences using inline CSS transitions. All changes are atomic — the margin panel and code bar are swapped in one commit.

**Tech Stack:** Jinja2 templates, vanilla JS, CSS, Python (FastAPI)

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `src/ace/services/coding_render.py` | Delete `build_margin_annotations()` | Modify |
| `tests/test_services/test_coding_render.py` | Delete margin tests | Modify |
| `src/ace/routes/pages.py` | Replace `margin_annotations` with `margin_codes` | Modify |
| `src/ace/routes/api.py` | Remove margin panel from 3 OOB helpers | Modify |
| `src/ace/templates/coding.html` | Remove margin block, add code bar in text panel | Modify |
| `src/ace/static/css/coding.css` | Remove margin + flash CSS, add code bar CSS | Modify |
| `src/ace/static/js/bridge.js` | Remove positioning JS, add chip flash handler | Modify |

---

### Task 1: Delete margin panel backend + add margin_codes

Remove `build_margin_annotations()`, its tests, OOB helpers, and replace with a simple deduped code list.

**Files:**
- Modify: `src/ace/services/coding_render.py`
- Modify: `tests/test_services/test_coding_render.py`
- Modify: `src/ace/routes/pages.py`
- Modify: `src/ace/routes/api.py`

- [ ] **Step 1: Delete `build_margin_annotations()` from coding_render.py**

In `src/ace/services/coding_render.py`, delete the entire function (lines 66–131, everything from `def build_margin_annotations` through the end of the file).

- [ ] **Step 2: Delete margin tests from test file**

In `tests/test_services/test_coding_render.py`, delete everything from line 112 onward (the `from ace.services.coding_render import build_margin_annotations` import, the helpers `_units`, `_ann`, `_CODES`, and all 9 `test_margin_*` functions).

- [ ] **Step 3: Replace `margin_annotations` with `margin_codes` in pages.py**

In `src/ace/routes/pages.py`:

**3a.** Remove the `build_margin_annotations` import (line 58). Change:
```python
    from ace.services.coding_render import (
        build_margin_annotations,
        render_sentence_text,
    )
```
To:
```python
    from ace.services.coding_render import render_sentence_text
```

**3b.** Replace the margin_annotations computation (lines 133–136) with a simple dedup:
```python
    # Deduplicated codes applied to this source (for bottom code bar)
    seen_codes: set[str] = set()
    margin_codes: list[dict] = []
    for ann in annotations_list:
        cid = ann["code_id"]
        if cid not in seen_codes:
            code = codes_by_id.get(cid)
            if code:
                seen_codes.add(cid)
                margin_codes.append({
                    "code_id": cid,
                    "code_name": code["name"],
                    "colour": code["colour"],
                })
```

**3c.** In the return dict, replace `"margin_annotations": margin_annotations,` (line 182) with `"margin_codes": margin_codes,`.

- [ ] **Step 4: Remove margin panel from OOB helpers in api.py**

**4a. `_render_coding_oob()`** (lines 528–540): Remove the margin_html render and OOB injection. Change the docstring and return:

```python
def _render_coding_oob(request: Request, conn, coder_id: str, current_index: int) -> str:
    """Render text_panel (primary) + annotation data (OOB)."""
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    ctx = _coding_context(conn, coder_id, current_index)
    ctx["request"] = request

    text_html = render_block(templates.env, "coding.html", "text_panel", ctx)

    return text_html + _render_ann_data_oob(ctx)
```

**4b. `_render_full_coding_oob()`** (lines 543–568): Remove `("margin_panel", "margin-panel")` from the `oob_blocks` list (line 556). The list becomes:

```python
    oob_blocks = [
        ("coding_header", "coding-header"),
        ("source_grid", "source-grid-overlay"),
        ("code_sidebar", "code-sidebar"),
    ]
```

**4c. `_render_sidebar_and_text()`** (lines 1015–1034): Remove the margin_html render and OOB injection. The function becomes:

```python
def _render_sidebar_and_text(request: Request, conn, coder_id: str, current_index: int) -> str:
    """Render code sidebar (primary) + OOB text panel + OOB code-colours + annotation data."""
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    ctx = _coding_context(conn, coder_id, current_index)
    ctx["request"] = request

    sidebar_html = render_block(templates.env, "coding.html", "code_sidebar", ctx)
    text_html = render_block(templates.env, "coding.html", "text_panel", ctx)

    return (
        sidebar_html
        + _inject_oob(text_html, "text-panel")
        + _render_colour_style_oob(ctx["codes"])
        + _render_ann_data_oob(ctx)
    )
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest`
Expected: Tests pass (count drops by 9 from deleted margin tests). The app will have a broken template until Task 2, but server-side tests don't render templates.

- [ ] **Step 6: Do NOT commit yet** — Task 2 updates the template. Commit all tasks together.

---

### Task 2: Template + CSS — remove margin panel, add code bar

**Files:**
- Modify: `src/ace/templates/coding.html`
- Modify: `src/ace/static/css/coding.css`

- [ ] **Step 1: Remove margin panel block and add code bar inside text panel**

In `src/ace/templates/coding.html`, replace lines 119–166 (from `{# Centre: text panel #}` through the closing `</div>` of `#content-scroll`) with:

```html
      {# Centre: text panel #}
      {% block text_panel %}
      <div id="text-panel" class="ace-text-panel" tabindex="0">
        <div class="ace-text-nav">
          <div class="ace-nav-cluster">
            <button class="ace-nav-btn" id="btn-prev"
                    {% if current_index <= 0 %}disabled{% endif %}
                    onclick="aceNavigatePrev()">&#8249;</button>
            <span class="ace-nav-counter" id="nav-counter"
                  onclick="aceToggleGrid()" title="Open source grid">
              <span class="ace-status-badge ace-status-badge--{{ current_status }}"></span>
              {{ current_index + 1 }} / {{ total_sources }} &#9783;
            </span>
            <button class="ace-nav-btn" id="btn-next"
                    {% if current_index >= total_sources - 1 %}disabled{% endif %}
                    onclick="aceNavigateNext()">&#8250;</button>
          </div>
        </div>
        {% if sentence_html %}
        {{ sentence_html | safe }}
        {% elif source_text %}
        <p>{{ source_text }}</p>
        {% else %}
        <p class="ace-text-empty">No source content.</p>
        {% endif %}
        {% if margin_codes %}
        <div class="ace-code-bar">
          <span class="ace-code-bar-label">Codes:</span>
          {% for code in margin_codes %}
          <span class="ace-code-chip" data-code-id="{{ code['code_id'] }}" data-colour="{{ code['colour'] }}">
            <span class="ace-code-chip-dot" style="background: {{ code['colour'] }};"></span>
            {{ code['code_name'] }}
          </span>
          {% endfor %}
        </div>
        {% endif %}
      </div>
      {% endblock %}

    </div>

  </div>
```

Key changes:
- `{% block margin_panel %}` and `<div id="margin-panel">` completely removed
- Code bar added at the bottom of `{% block text_panel %}`, after the sentence content
- `#content-scroll` wrapper now has one child (text panel only)

- [ ] **Step 2: Update CSS — remove margin + flash rules, add code bar rules**

In `src/ace/static/css/coding.css`:

**2a.** Delete all `.ace-margin-*` rules (lines 387–443) — everything from `/* ---- Right margin panel ---- */` through `.ace-margin-empty`.

**2b.** Delete `@keyframes ace-flash` and `.ace-flash` rules (lines 447–453).

**2c.** Add code bar styles where the margin rules were:

```css
/* ---- Bottom code bar ---- */

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

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All pass

- [ ] **Step 4: Do NOT commit yet** — Task 3 updates JS. Commit all tasks together.

---

### Task 3: JS — remove positioning, add chip flash handler

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Delete the margin click-flash handler**

In `bridge.js`, delete lines 680–700 (the `// Click on margin note to flash corresponding sentences` block inside the global click listener). This is the block from `var note = e.target.closest(".ace-margin-note")` through the closing `}` before `});`.

- [ ] **Step 2: Add chip click-flash handler**

In the same global click listener (right after the sentence click handler that ends around line 678), add:

```javascript
    // Click on code chip to flash corresponding sentences
    var chip = e.target.closest(".ace-code-chip");
    if (chip) {
      var codeId = chip.dataset.codeId;
      var colour = chip.dataset.colour || "#ffeb3b";
      var r = parseInt(colour.slice(1, 3), 16);
      var g = parseInt(colour.slice(3, 5), 16);
      var b = parseInt(colour.slice(5, 7), 16);

      // Read annotations from #ace-ann-data
      var dataEl = document.getElementById("ace-ann-data");
      if (!dataEl) return;
      var anns = JSON.parse(dataEl.dataset.annotations || "[]");
      var matching = anns.filter(function (a) { return a.code_id === codeId; });

      // Find overlapping sentences and flash them
      var sentences = document.querySelectorAll(".ace-sentence");
      var flashed = [];
      matching.forEach(function (ann) {
        sentences.forEach(function (s) {
          var ss = parseInt(s.dataset.start, 10);
          var se = parseInt(s.dataset.end, 10);
          if (ann.start < se && ann.end > ss && flashed.indexOf(s) < 0) {
            flashed.push(s);
          }
        });
      });

      // Flash each sentence with the code's colour
      flashed.forEach(function (s) {
        s.style.transition = "none";
        s.style.background = "rgba(" + r + "," + g + "," + b + ",0.5)";
        void s.offsetWidth;
        s.style.transition = "background 1.2s ease-out";
        s.style.background = "";
      });

      // Scroll first flashed sentence into view
      if (flashed.length) {
        flashed[0].scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
```

- [ ] **Step 3: Remove `_schedulePosition()` from afterSettle handler**

In the `htmx:afterSettle` handler (around line 709–712), remove `_schedulePosition();` from the text-panel branch. Change:
```javascript
    if (target.id === "text-panel" || target.id === "coding-workspace") {
      _restoreFocus();
      _paintHighlights();
      _schedulePosition();
    }
```
To:
```javascript
    if (target.id === "text-panel" || target.id === "coding-workspace") {
      _restoreFocus();
      _paintHighlights();
    }
```

- [ ] **Step 4: Remove `_schedulePosition()` from pointerup handler**

In the sidebar resize `pointerup` handler (around line 593), delete the `_schedulePosition();` line.

- [ ] **Step 5: Delete section 19 (margin card positioning)**

Delete the entire section 19 block (lines 1354–1413) — everything from `/* 19. Margin card positioning */` through `_schedulePosition()`.

- [ ] **Step 6: Remove margin positioning from DOMContentLoaded**

In the DOMContentLoaded handler, delete `_positionMarginCards();` (around line 1425). Also delete the ResizeObserver setup (around lines 1435–1439):
```javascript
    // Re-position margin cards on container resize
    var scrollWrapper = document.getElementById("content-scroll");
    if (scrollWrapper && typeof ResizeObserver !== "undefined") {
      new ResizeObserver(_schedulePosition).observe(scrollWrapper);
    }
```

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest`
Expected: All pass

- [ ] **Step 8: Commit all tasks together**

```bash
git add src/ace/services/coding_render.py tests/test_services/test_coding_render.py src/ace/routes/pages.py src/ace/routes/api.py src/ace/templates/coding.html src/ace/static/css/coding.css src/ace/static/js/bridge.js
git commit -m "feat: replace margin panel with sticky bottom code bar"
```

---

### Task 4: Visual verification

**Files:** Any files from Tasks 1–3 that need adjustment.

- [ ] **Step 1: Start the dev server**

Run: `uv run uvicorn ace.app:create_app --factory --host 127.0.0.1 --port 8080 --reload --reload-dir src/ace`

- [ ] **Step 2: Verify code bar**

Open `http://127.0.0.1:8080/code` in a browser. Test:

1. **Bar visible** — code chips appear at the bottom of the text panel
2. **Sticky** — scroll down on a long source, the bar stays at the bottom of the viewport
3. **Chip content** — each chip shows a colour dot + code name
4. **Click flash** — click a chip → its coded sentences flash with that code's colour, then fade
5. **Scroll to first** — clicking a chip scrolls the first matching sentence into view
6. **Apply new code** — press a hotkey → chip appears in the bar
7. **Undo** — press Z → chip disappears from the bar (if no annotations of that code remain)
8. **No margin panel** — the right side has no panel, text takes full width
9. **Empty source** — navigate to an uncoded source → no code bar visible

- [ ] **Step 3: Fix any visual issues**

Common issues:
- Bar not sticky → check `position: sticky; bottom: 0` and that parent has `overflow-y: auto`
- Flash not working → check `#ace-ann-data` has data, check hex-to-rgb parsing
- Chips not updating → check the code bar is inside `{% block text_panel %}`
- Layout broken → check margin panel CSS fully removed, `#content-scroll` flex still works

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: visual adjustments for bottom code bar"
```

(Skip if no fixes needed.)
