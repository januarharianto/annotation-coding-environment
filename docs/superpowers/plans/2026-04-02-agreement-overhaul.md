# Agreement Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the multi-step agreement dashboard with a streamlined flow: choose files → auto-compute → minimalist results page with tables, references, and raw data export.

**Architecture:** Three layers of change: (1) computation fixes in `agreement_computer.py` (pooled overall, n_sources, expanded pairwise), (2) template/CSS rebuild for the results page, (3) API endpoint rewrites for HTML rendering and new raw export. The `AgreementLoader` and data pipeline are unchanged — only what happens after `compute_agreement()` returns, plus how the overall is computed inside it.

**Tech Stack:** Python (FastAPI, irrCAC, krippendorff), Jinja2, vanilla CSS, HTMX, existing Sortable.js file picker

**Spec:** `docs/superpowers/specs/2026-04-01-agreement-overhaul.md`

---

### Task 1: Computation — Pooled Overall + n_sources

**Files:**
- Modify: `src/ace/services/agreement_types.py:45-53`
- Modify: `src/ace/services/agreement_computer.py:18-116, 250-271`
- Test: `tests/test_agreement_computer.py`

- [ ] **Step 1: Add n_sources to CodeMetrics**

In `src/ace/services/agreement_types.py`, add `n_sources` field to the `CodeMetrics` dataclass:

```python
@dataclass
class CodeMetrics:
    percent_agreement: float
    n_positions: int
    n_sources: int = 0
    cohens_kappa: float | None = None
    krippendorffs_alpha: float | None = None
    fleiss_kappa: float | None = None
    congers_kappa: float | None = None
    gwets_ac1: float | None = None
    brennan_prediger: float | None = None
```

- [ ] **Step 2: Write failing test — pooled overall differs from macro-average**

Add to `tests/test_agreement_computer.py`:

```python
def test_overall_is_pooled_not_macro_averaged():
    """Overall metrics should be computed on pooled data, not averaged per-code."""
    # Create dataset with 2 codes: one with high agreement (many positions),
    # one with low agreement (few positions). Pooled should weight the high one more.
    sources = [MatchedSource(content_hash="h1", display_id="S1", content_text="a" * 100)]
    coders = [
        CoderInfo(id="c1", label="Alice", source_file="a.ace"),
        CoderInfo(id="c2", label="Bob", source_file="b.ace"),
    ]
    codes = [
        MatchedCode(name="CodeA", present_in={"c1", "c2"}),
        MatchedCode(name="CodeB", present_in={"c1", "c2"}),
    ]
    # CodeA: both coders agree on chars 0-79 (80 chars)
    # CodeB: coders disagree entirely (c1: 90-94, c2: 95-99) — 10 chars each, no overlap
    annotations = [
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="CodeA", start_offset=0, end_offset=80),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="CodeA", start_offset=0, end_offset=80),
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="CodeB", start_offset=90, end_offset=95),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="CodeB", start_offset=95, end_offset=100),
    ]
    dataset = AgreementDataset(
        sources=sources, coders=coders, codes=codes,
        annotations=annotations, warnings=[],
    )
    result = compute_agreement(dataset)

    # Pooled overall should be higher than a simple average of per-code metrics
    # because CodeA (high agreement) has many more positions than CodeB (low agreement)
    code_a_alpha = result.per_code["CodeA"].krippendorffs_alpha
    code_b_alpha = result.per_code["CodeB"].krippendorffs_alpha
    macro_avg = (code_a_alpha + code_b_alpha) / 2 if code_a_alpha and code_b_alpha else 0

    assert result.overall.krippendorffs_alpha is not None
    # Pooled should NOT equal the macro average
    if code_a_alpha and code_b_alpha:
        assert abs(result.overall.krippendorffs_alpha - macro_avg) > 0.01
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_agreement_computer.py::test_overall_is_pooled_not_macro_averaged -v`
Expected: FAIL — current overall IS macro-averaged.

- [ ] **Step 4: Implement pooled overall and n_sources**

In `src/ace/services/agreement_computer.py`, replace the overall computation in `compute_agreement()`. Find line ~103 where `overall = _macro_average(...)` is called. Replace the overall computation with pooled logic:

```python
    # Compute overall by pooling all code vectors into one combined dataset
    pooled_vectors: dict[str, list[int]] = {cid: [] for cid in coder_ids}
    for code_name in per_code_vectors:
        for cid in coder_ids:
            pooled_vectors[cid].extend(per_code_vectors[code_name][cid])
    overall = _compute_metrics(pooled_vectors, coder_ids)
    overall.n_sources = len(dataset.sources)
```

Also, add n_sources computation in the per-code loop. After building `per_code_results`, compute n_sources for each code. Find where per-code metrics are built (around line 92-95) and add:

```python
    # Count sources per code
    code_sources: dict[str, set[str]] = {}
    for ann in dataset.annotations:
        code_sources.setdefault(ann.code_name, set()).add(ann.source_hash)

    for code_name, metrics in per_code_results.items():
        metrics.n_sources = len(code_sources.get(code_name, set()))
```

- [ ] **Step 5: Update _compute_metrics to return n_sources=0 by default**

The `_compute_metrics` function returns a `CodeMetrics`. Since `n_sources` defaults to 0, no change is needed in `_compute_metrics` itself — callers set it after.

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_agreement_computer.py -v`
Expected: All tests pass including the new one.

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass. Some agreement route tests may need updating if they assert on specific overall values.

- [ ] **Step 8: Commit**

```bash
git add src/ace/services/agreement_types.py src/ace/services/agreement_computer.py tests/test_agreement_computer.py
git commit -m "feat: pooled overall computation and n_sources per code"
```

---

### Task 2: Computation — Expanded Pairwise

**Files:**
- Modify: `src/ace/services/agreement_types.py:56-64`
- Modify: `src/ace/services/agreement_computer.py:274-293`
- Test: `tests/test_agreement_computer.py`

- [ ] **Step 1: Update AgreementResult pairwise type**

In `src/ace/services/agreement_types.py`, change the `pairwise` field from `dict[tuple, float]` to `dict[tuple, CodeMetrics]`:

```python
@dataclass
class AgreementResult:
    overall: CodeMetrics
    per_code: dict[str, CodeMetrics]
    per_source: dict[str, CodeMetrics]
    pairwise: dict[tuple[str, str], CodeMetrics]  # Changed: was float (alpha only)
    n_coders: int
    n_sources: int
    n_codes: int
```

- [ ] **Step 2: Write failing test — pairwise returns full metrics**

Add to `tests/test_agreement_computer.py`:

```python
def test_pairwise_returns_full_metrics():
    """Pairwise should return CodeMetrics (%, alpha, kappa, AC1), not just alpha."""
    sources = [MatchedSource(content_hash="h1", display_id="S1", content_text="a" * 50)]
    coders = [
        CoderInfo(id="c1", label="Alice", source_file="a.ace"),
        CoderInfo(id="c2", label="Bob", source_file="b.ace"),
        CoderInfo(id="c3", label="Carol", source_file="c.ace"),
    ]
    codes = [MatchedCode(name="Code1", present_in={"c1", "c2", "c3"})]
    annotations = [
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="Code1", start_offset=0, end_offset=30),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="Code1", start_offset=0, end_offset=30),
        MatchedAnnotation(source_hash="h1", coder_id="c3", code_name="Code1", start_offset=10, end_offset=40),
    ]
    dataset = AgreementDataset(
        sources=sources, coders=coders, codes=codes,
        annotations=annotations, warnings=[],
    )
    result = compute_agreement(dataset)

    assert len(result.pairwise) == 3  # 3 pairs for 3 coders
    for pair_key, metrics in result.pairwise.items():
        assert isinstance(metrics, CodeMetrics)
        assert metrics.percent_agreement is not None
        assert metrics.krippendorffs_alpha is not None
        # Cohen's kappa should be computed for each pair (2 coders)
        assert metrics.cohens_kappa is not None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_agreement_computer.py::test_pairwise_returns_full_metrics -v`
Expected: FAIL — current pairwise returns float, not CodeMetrics.

- [ ] **Step 4: Rewrite _compute_pairwise to return full CodeMetrics**

Replace `_compute_pairwise` in `agreement_computer.py` (lines 274-293):

```python
def _compute_pairwise(
    per_code_vectors: dict[str, dict[str, list[int]]],
    coder_ids: list[str],
) -> dict[tuple[str, str], "CodeMetrics"]:
    """Compute full agreement metrics for each coder pair, pooled across codes."""
    results: dict[tuple[str, str], CodeMetrics] = {}
    for i, cid_a in enumerate(coder_ids):
        for cid_b in coder_ids[i + 1 :]:
            # Pool vectors across all codes for this pair
            pair_vectors: dict[str, list[int]] = {cid_a: [], cid_b: []}
            for code_vectors in per_code_vectors.values():
                if cid_a in code_vectors and cid_b in code_vectors:
                    pair_vectors[cid_a].extend(code_vectors[cid_a])
                    pair_vectors[cid_b].extend(code_vectors[cid_b])

            if not pair_vectors[cid_a]:
                continue

            metrics = _compute_metrics(pair_vectors, [cid_a, cid_b])
            results[(cid_a, cid_b)] = metrics
    return results
```

- [ ] **Step 5: Update any code that reads pairwise values**

Search for uses of `result.pairwise` in the codebase. The compute endpoint in api.py accesses pairwise values — those will be updated in Task 4. For now, fix any test assertions that expect `float` instead of `CodeMetrics`:

```bash
grep -rn "result.pairwise\|\.pairwise\[" tests/ src/
```

Fix each occurrence. In `test_agreement_computer.py`, the existing `test_pairwise_alpha` test likely asserts `isinstance(val, float)` — update to check `val.krippendorffs_alpha`.

- [ ] **Step 6: Run tests**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/ace/services/agreement_types.py src/ace/services/agreement_computer.py tests/test_agreement_computer.py
git commit -m "feat: expanded pairwise — full CodeMetrics per pair (%, alpha, kappa, AC1)"
```

---

### Task 3: Template + CSS + JS — Page Shell

**Files:**
- Modify: `src/ace/templates/agreement.html`
- Modify: `src/ace/static/css/agreement.css`

- [ ] **Step 1: Rebuild agreement.html template**

Replace the entire content of `src/ace/templates/agreement.html` with:

```html
{% extends "base.html" %}

{% block title %}Agreement — ACE{% endblock %}

{% block head %}
<link rel="stylesheet" href="/static/css/agreement.css">
{% endblock %}

{% block content %}
<div class="ace-agreement-page">
  <a href="/" class="ace-back">← Home</a>

  <div id="agreement-results">
    {# Empty state — shown on page load #}
    <h1 class="ace-agreement-title">Inter-Coder Agreement</h1>
    <div class="ace-agreement-empty">
      <p>Select 2 or more .ace files to compute agreement</p>
      <button class="ace-agreement-choose-btn" onclick="acePickAndCompute()">Choose files</button>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script>
(function() {
  "use strict";

  window.acePickAndCompute = function() {
    // Show loading state
    var results = document.getElementById("agreement-results");
    results.innerHTML =
      '<h1 class="ace-agreement-title">Inter-Coder Agreement</h1>' +
      '<div class="ace-agreement-loading" role="status" aria-live="polite">Computing agreement\u2026</div>';

    fetch("/api/native/pick-files", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "accept=.ace&multiple=true"
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data.paths || data.paths.length < 2) {
          // Cancelled or too few files — restore empty state
          results.innerHTML =
            '<h1 class="ace-agreement-title">Inter-Coder Agreement</h1>' +
            '<div class="ace-agreement-empty">' +
            '<p>Select 2 or more .ace files to compute agreement</p>' +
            '<button class="ace-agreement-choose-btn" onclick="acePickAndCompute()">Choose files</button>' +
            '</div>';
          return;
        }
        // Auto-compute: POST paths to compute endpoint
        htmx.ajax("POST", "/api/agreement/compute", {
          values: { paths: JSON.stringify(data.paths) },
          target: "#agreement-results",
          swap: "innerHTML",
        });
      })
      .catch(function() {
        results.innerHTML =
          '<h1 class="ace-agreement-title">Inter-Coder Agreement</h1>' +
          '<div class="ace-agreement-error">' +
          '<p>Something went wrong. Please try again.</p>' +
          '<button class="ace-agreement-choose-btn" onclick="acePickAndCompute()">Choose different files</button>' +
          '</div>';
      });
  };
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Rebuild agreement.css**

Replace the entire content of `src/ace/static/css/agreement.css` with:

```css
/* Agreement results page */

.ace-agreement-page {
  max-width: 820px;
  margin: 0 auto;
  padding: 32px 24px;
}

.ace-agreement-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
}

/* Title bar with export buttons */
.ace-agreement-title-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 0 4px;
}

.ace-agreement-title-bar .ace-agreement-title { flex: 0 0 auto; }
.ace-agreement-title-bar .spacer { flex: 1; }

.ace-export-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 500;
  color: var(--ace-text);
  background: var(--ace-bg-muted);
  border: 1px solid var(--ace-border);
  border-radius: var(--ace-radius);
  text-decoration: none;
  transition: background var(--ace-transition);
}

.ace-export-pill:hover { background: var(--ace-border-light); }

/* Context bar */
.ace-agreement-context {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--ace-border);
  font-size: var(--ace-font-size-sm);
  color: var(--ace-text-muted);
  margin-bottom: 8px;
}

.ace-agreement-context strong { color: var(--ace-text); }
.ace-agreement-context .dot { color: var(--ace-border-light); }
.ace-agreement-context .action {
  margin-left: auto;
  color: var(--ace-text-muted);
  text-decoration: none;
  font-size: var(--ace-font-size-xs);
}
.ace-agreement-context .action:hover { color: var(--ace-text); }

/* Warnings */
.ace-agreement-warnings { margin-bottom: 16px; font-size: var(--ace-font-size-xs); }
.ace-agreement-warnings summary { cursor: pointer; color: #92400e; padding: 2px 0; }
.ace-agreement-warn-body {
  padding: 8px 12px;
  margin-top: 4px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: var(--ace-radius);
  line-height: 1.7;
  color: var(--ace-text-muted);
}
.ace-agreement-warn-body strong { color: var(--ace-text); }

/* Table wrapper for horizontal scroll */
.ace-table-scroll { overflow-x: auto; margin-bottom: 24px; }

/* Metrics table */
.ace-agreement-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--ace-font-size-sm);
  font-variant-numeric: tabular-nums lining-nums;
}

.ace-agreement-table caption {
  text-align: left;
  font-size: var(--ace-font-size-2xs);
  color: var(--ace-text-muted);
  letter-spacing: 0.5px;
  text-transform: uppercase;
  padding-bottom: 8px;
  caption-side: top;
}

.ace-agreement-table th {
  text-align: right;
  padding: 6px 8px;
  font-weight: 600;
  border-bottom: 2px solid var(--ace-border);
}

.ace-agreement-table th:first-child { text-align: left; }
.ace-agreement-table th.col-primary { color: var(--ace-text-muted); }
.ace-agreement-table th.col-muted { color: #9ca3af; }
.ace-agreement-table th.col-gap { padding-left: 20px; }

.ace-agreement-table td {
  text-align: right;
  padding: 5px 8px;
  border-bottom: 1px solid var(--ace-border-light);
}

.ace-agreement-table td:first-child {
  text-align: left;
  position: sticky;
  left: 0;
  background: var(--ace-bg);
  z-index: 1;
}

.ace-agreement-table td.col-gap { padding-left: 20px; }
.ace-agreement-table .col-val-primary { color: var(--ace-text); }
.ace-agreement-table .col-val-muted { color: #757575; }
.ace-agreement-table .col-val-faint { color: var(--ace-text-muted); }
.ace-agreement-table .col-val-low { color: #9a3412; }

.ace-agreement-table .interp {
  display: block;
  font-size: 9px;
  color: #b0b8c4;
  line-height: 1;
  margin-top: 1px;
  font-variant-numeric: normal;
}

/* Overall row */
.ace-agreement-table .overall-row td {
  font-weight: 700;
  border-top: 2px solid var(--ace-border);
  background: var(--ace-bg-muted);
  padding: 7px 8px;
}

/* Reference superscripts */
.ace-ref-sup {
  font-size: 9px;
  color: #b0b8c4;
  vertical-align: super;
  margin-left: 1px;
}

/* References list */
.ace-agreement-refs {
  border-top: 1px solid var(--ace-border);
  padding-top: 16px;
  font-size: var(--ace-font-size-2xs);
  color: var(--ace-text-muted);
  line-height: 1.7;
}

.ace-agreement-refs h2 {
  font-size: var(--ace-font-size-2xs);
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--ace-text-muted);
  font-weight: 600;
  margin-bottom: 8px;
}

.ace-agreement-refs ol { padding-left: 18px; margin: 0; }
.ace-agreement-refs li { margin-bottom: 3px; }
.ace-agreement-refs .ref-author { color: var(--ace-text-muted); }
.ace-agreement-refs .ref-journal { color: var(--ace-text-muted); }

/* Empty / loading / error states */
.ace-agreement-empty,
.ace-agreement-loading,
.ace-agreement-error {
  text-align: center;
  padding: 80px 24px;
  color: var(--ace-text-muted);
}

.ace-agreement-empty p,
.ace-agreement-error p {
  font-size: var(--ace-font-size-base);
  margin-bottom: 16px;
}

.ace-agreement-choose-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  font-size: var(--ace-font-size-sm);
  font-weight: 500;
  color: var(--ace-text);
  background: var(--ace-bg-muted);
  border: 1px solid var(--ace-border);
  border-radius: var(--ace-radius);
  cursor: pointer;
  transition: background var(--ace-transition);
}

.ace-agreement-choose-btn:hover { background: var(--ace-border-light); }

.ace-agreement-loading {
  font-size: var(--ace-font-size-sm);
}
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest -x -q`
Expected: All tests pass. The route test `test_agreement_page_renders` may need updating if it asserts on old HTML structure.

- [ ] **Step 4: Commit**

```bash
git add src/ace/templates/agreement.html src/ace/static/css/agreement.css
git commit -m "feat: rebuild agreement template — empty/loading/error states, new CSS"
```

---

### Task 4: API — Rewrite Compute Endpoint HTML Rendering

**Files:**
- Modify: `src/ace/routes/api.py:1350-1488`
- Test: `tests/test_agreement_routes.py`

This is the largest task — the compute endpoint currently builds ~130 lines of inline HTML. Replace it with the new minimalist rendering.

- [ ] **Step 1: Write test for new results HTML structure**

Add to `tests/test_agreement_routes.py`:

```python
def test_compute_returns_new_results_structure(agreement_client):
    """Compute returns title bar, context, table with Overall row, and references."""
    client = agreement_client
    resp = client.post("/api/agreement/compute", data={"paths": json.dumps(client._ace_paths)})
    assert resp.status_code == 200
    html = resp.text
    # Title bar with exports
    assert "ace-agreement-title-bar" in html
    assert "Summary CSV" in html
    assert "Raw data CSV" in html
    # Context bar
    assert "ace-agreement-context" in html
    assert "coders" in html
    # Metrics table with Overall row
    assert "Overall (pooled)" in html
    assert "ace-agreement-table" in html
    # References
    assert "ace-agreement-refs" in html
    assert "Krippendorff" in html
```

Note: The test fixture `agreement_client` must be set up with 2+ loaded files. Check the existing test file for how this is done and reuse the pattern.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agreement_routes.py::test_compute_returns_new_results_structure -v`
Expected: FAIL — current HTML doesn't have these classes.

- [ ] **Step 3: Rewrite the compute endpoint HTML rendering**

In `src/ace/routes/api.py`, find the `agreement_compute` function (POST /api/agreement/compute, around line 1350). The function currently accepts no `paths` parameter and relies on pre-loaded files. Update it to:

1. Accept `paths` as a JSON-encoded form parameter
2. Load the files, build the dataset, compute agreement
3. Return the new HTML structure

Replace the entire function body (keeping the route decorator). The new function should:

- Parse `paths` from the form data
- Load each file via the AgreementLoader
- Build the dataset and compute agreement
- Build HTML string with: title bar (with export links), context bar, warnings, metrics table, pairwise table, references
- Return HTMLResponse

The HTML rendering should use helper functions for each section. Key rendering logic:

**Interpretation label helper:**
```python
def _interp_label(alpha: float | None) -> str:
    if alpha is None:
        return ""
    if alpha < 0:
        return "poor"
    if alpha <= 0.20:
        return "slight"
    if alpha <= 0.40:
        return "fair"
    if alpha <= 0.60:
        return "moderate"
    if alpha <= 0.80:
        return "substantial"
    return "almost perfect"
```

**Format helper:**
```python
def _fmt(val: float | None, decimals: int = 2, is_pct: bool = False) -> str:
    if val is None:
        return "–"
    if is_pct:
        return f"{val * 100:.1f}"
    return f"{val:.{decimals}f}"
```

**Metrics table row helper** (for both per-code and overall):
```python
def _metrics_row(label, m, is_overall=False, kappa_col="fleiss", n_coders=2):
    """Build a table row for CodeMetrics."""
    cls = ' class="overall-row"' if is_overall else ""
    kappa_val = m.cohens_kappa if n_coders == 2 else m.fleiss_kappa
    alpha_label = _interp_label(m.krippendorffs_alpha)
    interp_html = f'<span class="interp">{alpha_label}</span>' if alpha_label else ""

    return f"""<tr{cls}>
      <td>{html.escape(label)}</td>
      <td class="col-val-primary">{_fmt(m.percent_agreement, is_pct=True)}</td>
      <td class="col-val-primary">{_fmt(m.krippendorffs_alpha)}{interp_html}</td>
      <td class="col-val-primary">{_fmt(kappa_val)}</td>
      <td class="col-val-muted col-gap">{_fmt(m.gwets_ac1)}</td>
      <td class="col-val-muted">{_fmt(m.congers_kappa)}</td>
      <td class="col-val-muted">{_fmt(m.brennan_prediger)}</td>
      <td class="col-val-faint">{m.n_sources}</td>
    </tr>"""
```

**References HTML** — read from the bib file at `src/ace/static/agreement_references.bib` and format as an ordered list. For simplicity, hardcode the reference list since it's static:

```python
AGREEMENT_REFERENCES = [
    "Holsti, O. R. (1969). <em>Content Analysis for the Social Sciences and Humanities.</em> Addison-Wesley.",
    "Krippendorff, K. (2011). Computing Krippendorff's alpha-reliability. <em>Annenberg School for Communication Departmental Papers, 43.</em>",
    "Cohen, J. (1960). A coefficient of agreement for nominal scales. <em>Educational and Psychological Measurement, 20</em>(1), 37–46.",
    "Fleiss, J. L. (1971). Measuring nominal scale agreement among many raters. <em>Psychological Bulletin, 76</em>(5), 378–382.",
    "Conger, A. J. (1980). Integration and generalization of kappas for multiple raters. <em>Psychological Bulletin, 88</em>(2), 322–328.",
    "Gwet, K. L. (2008). Computing inter-rater reliability and its variance in the presence of high agreement. <em>British Journal of Mathematical and Statistical Psychology, 61</em>(1), 29–48.",
    "Brennan, R. L., &amp; Prediger, D. J. (1981). Coefficient kappa: Some uses, misuses, and alternatives. <em>Educational and Psychological Measurement, 41</em>(3), 687–699.",
    "Landis, J. R., &amp; Koch, G. G. (1977). The measurement of observer agreement for categorical data. <em>Biometrics, 33</em>(1), 159–174.",
]
```

Assemble the full HTML response from these pieces. The endpoint should also handle the "Choose different files" flow by accepting new paths and recomputing.

- [ ] **Step 4: Update the agreement_compute route signature**

The current route accepts no parameters. Update to accept `paths`:

```python
@router.post("/agreement/compute")
async def agreement_compute(
    request: Request,
    paths: str = Form(...),
):
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest -x -q`
Expected: All tests pass. Update any existing agreement route tests that assert on old HTML structure.

- [ ] **Step 6: Verify in browser**

Open http://127.0.0.1:8080/agreement:
- Empty state with "Choose files" button
- Click "Choose files" → file picker opens
- Select 2+ .ace files → loading state → results render
- Title bar with export pills
- Context bar with counts
- Metrics table with all 7 metrics, interpretation labels, Overall at bottom
- Pairwise table (if 3+ coders)
- References at bottom
- "Choose different files" re-opens picker

- [ ] **Step 7: Commit**

```bash
git add src/ace/routes/api.py tests/test_agreement_routes.py
git commit -m "feat: rewrite agreement compute — minimalist results with tables and references"
```

---

### Task 5: Export Endpoints

**Files:**
- Modify: `src/ace/routes/api.py` (export/results endpoint)
- Create: new raw data export endpoint in `src/ace/routes/api.py`
- Test: `tests/test_agreement_routes.py`

- [ ] **Step 1: Write test for updated summary CSV**

```python
def test_export_summary_csv_has_overall_and_n_sources(agreement_client):
    """Summary CSV includes Overall row and n_sources column."""
    client = agreement_client
    # Compute first
    client.post("/api/agreement/compute", data={"paths": json.dumps(client._ace_paths)})
    resp = client.get("/api/agreement/export/results")
    assert resp.status_code == 200
    text = resp.text
    # Has metadata comment
    assert text.startswith("#")
    # Has n_sources column
    assert "n_sources" in text
    # Has Overall row
    assert "Overall" in text
```

- [ ] **Step 2: Write test for raw data CSV**

```python
def test_export_raw_data_csv(agreement_client):
    """Raw data CSV has source_id, start_offset, end_offset, coder_id, code_name columns."""
    client = agreement_client
    client.post("/api/agreement/compute", data={"paths": json.dumps(client._ace_paths)})
    resp = client.get("/api/agreement/export/raw")
    assert resp.status_code == 200
    text = resp.text
    assert "source_id" in text
    assert "start_offset" in text
    assert "end_offset" in text
    assert "coder_id" in text
    assert "code_name" in text
    assert resp.headers["content-type"].startswith("text/csv")
```

- [ ] **Step 3: Update summary CSV export**

In `src/ace/routes/api.py`, update `agreement_export_results` to:
1. Add metadata comment header (date, files, coders, counts)
2. Add `n_sources` column
3. Add Overall row at the end

- [ ] **Step 4: Add raw data CSV export endpoint**

Add a new endpoint:

```python
@router.get("/agreement/export/raw")
async def agreement_export_raw(request: Request):
    """Export raw annotation data as long-form CSV for reproducibility in R/Python."""
    import csv
    import io
    from datetime import date

    loader = getattr(request.app.state, "agreement_loader", None)
    if loader is None or loader.file_count < 2:
        return HTMLResponse("No agreement data available.", status_code=400)

    dataset = loader.build_dataset()

    output = io.StringIO()
    # Metadata header
    coder_labels = ", ".join(c.label for c in dataset.coders)
    output.write(f"# ACE raw agreement data — {date.today().isoformat()}\n")
    output.write(f"# Coders: {coder_labels}\n")
    output.write(f"# Sources: {len(dataset.sources)}, Codes: {len(dataset.codes)}\n")

    writer = csv.writer(output)
    writer.writerow(["source_id", "start_offset", "end_offset", "coder_id", "code_name"])

    # Build source hash → display_id lookup
    source_lookup = {s.content_hash: s.display_id for s in dataset.sources}

    for ann in sorted(dataset.annotations, key=lambda a: (a.source_hash, a.start_offset, a.coder_id)):
        source_id = source_lookup.get(ann.source_hash, ann.source_hash)
        writer.writerow([source_id, ann.start_offset, ann.end_offset, ann.coder_id, ann.code_name])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="agreement_raw_data.csv"'},
    )
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/ace/routes/api.py tests/test_agreement_routes.py
git commit -m "feat: updated summary CSV with metadata + new raw data CSV export"
```

---

### Task 6: Integration Test + Cleanup

**Files:**
- Modify: `tests/test_agreement_routes.py`
- Modify: `src/ace/routes/api.py` (cleanup unused endpoints)

- [ ] **Step 1: Remove unused endpoints**

The old flow used `POST /api/agreement/add-file` and `POST /api/agreement/reset` as separate steps. With the new auto-compute flow, `add-file` is no longer called from the template. Remove or keep based on whether tests still use them. If the compute endpoint now handles loading internally, `add-file` may be dead code.

Check:
```bash
grep -rn "agreement/add-file\|agreement/reset" src/ace/templates/ src/ace/static/
```

If only referenced in tests and old template, the endpoints can stay (they don't hurt) but the old template JS that called them is gone.

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 3: Verify complete flow in browser**

Full walkthrough:
1. Navigate to http://127.0.0.1:8080/agreement
2. See empty state with "Choose files" button
3. Click button → file picker opens
4. Select 2 .ace files → loading indicator → results render
5. Title bar: "Inter-Coder Agreement" + ↓ Summary CSV + ↓ Raw data CSV
6. Context bar: coder count, source counts (N of M), code counts
7. Warnings: collapsible if any mismatches
8. Metrics table: all 7 columns, interpretation labels on α, Overall row at bottom
9. Pairwise table (if 3+ coders): flat list with %, α, Cohen κ, AC1
10. References section at bottom with numbered citations
11. Click ↓ Summary CSV → downloads CSV with metadata header + Overall row
12. Click ↓ Raw data CSV → downloads long-form span CSV
13. Click "Choose different files" → re-opens picker, new results replace old

- [ ] **Step 4: Commit**

```bash
git add src/ace/routes/api.py tests/test_agreement_routes.py
git commit -m "refactor: cleanup old agreement endpoints and add integration tests"
```
