# Inter-Coder Agreement Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only agreement dashboard that loads multiple `.ace` files, computes inter-coder reliability metrics, and presents publication-ready results with CSV export.

**Architecture:** Two services (AgreementLoader + AgreementComputer) following ACE's existing thin-page/fat-service pattern. The loader opens `.ace` files read-only, matches sources by content_hash and codes by name, and produces an `AgreementDataset`. The computer takes that dataset, builds character-level binary vectors, and computes all metrics (percent agreement, Cohen's/Fleiss' kappa, Krippendorff's alpha, Gwet's AC1, Brennan-Prediger, Conger's kappa). The `/agreement` page renders the dashboard.

**Tech Stack:** Python 3.12, NiceGUI (Quasar), SQLite3, scikit-learn, krippendorff, irrCAC, pandas

**Spec:** `docs/superpowers/specs/2026-03-14-agreement-dashboard-design.md`

---

## Chunk 1: Foundation — Data Structures, Loader, Dependencies

### Task 1: Add Dependencies

**Files:**
- Modify: `pyproject.toml:10-16`

- [ ] **Step 1: Add krippendorff and bump irrCAC**

In `pyproject.toml`, update the dependencies list:

```toml
dependencies = [
    "nicegui>=3.0",
    "pandas>=2.0",
    "openpyxl>=3.1",
    "irrCAC>=0.4",
    "scikit-learn>=1.0",
    "krippendorff>=0.7",
]
```

Changes: `irrCAC>=0.3` → `irrCAC>=0.4`, add `krippendorff>=0.7`.

- [ ] **Step 2: Sync dependencies**

Run: `uv sync`
Expected: Resolves and installs `krippendorff` package. `irrCAC` may update.

- [ ] **Step 3: Verify imports work**

Run: `uv run python -c "import krippendorff; from irrCAC.raw import CAC; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add krippendorff dependency, bump irrCAC to >=0.4"
```

---

### Task 2: Data Structures

**Files:**
- Create: `src/ace/services/agreement_types.py`
- Test: `tests/test_services/test_agreement_types.py`

- [ ] **Step 1: Write test for dataclass construction**

```python
"""Tests for agreement data structures."""

from ace.services.agreement_types import (
    AgreementDataset,
    AgreementResult,
    CodeMetrics,
    CoderInfo,
    MatchedAnnotation,
    MatchedCode,
    MatchedSource,
)


def test_matched_source_construction():
    src = MatchedSource(
        content_hash="abc123", display_id="S001", content_text="hello world"
    )
    assert src.content_hash == "abc123"
    assert src.display_id == "S001"
    assert src.content_text == "hello world"


def test_agreement_dataset_construction():
    ds = AgreementDataset(sources=[], coders=[], codes=[], annotations=[], warnings=[])
    assert ds.sources == []
    assert ds.warnings == []


def test_code_metrics_defaults():
    m = CodeMetrics(percent_agreement=0.85, n_positions=100)
    assert m.percent_agreement == 0.85
    assert m.cohens_kappa is None
    assert m.krippendorffs_alpha is None
    assert m.fleiss_kappa is None
    assert m.congers_kappa is None
    assert m.gwets_ac1 is None
    assert m.brennan_prediger is None


def test_agreement_result_construction():
    metrics = CodeMetrics(percent_agreement=0.9, n_positions=50)
    result = AgreementResult(
        overall=metrics,
        per_code={"Positive": metrics},
        per_source={"S001": metrics},
        pairwise={("c1", "c2"): 0.85},
        n_coders=2,
        n_sources=1,
        n_codes=1,
    )
    assert result.n_coders == 2
    assert result.pairwise[("c1", "c2")] == 0.85
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_services/test_agreement_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ace.services.agreement_types'`

- [ ] **Step 3: Write the data structures**

Create `src/ace/services/agreement_types.py`:

```python
"""Data structures for inter-coder agreement computation."""

from dataclasses import dataclass, field


@dataclass
class MatchedSource:
    content_hash: str
    display_id: str
    content_text: str


@dataclass
class CoderInfo:
    id: str  # unique across the comparison
    label: str  # display name (coder name or "Coder N")
    source_file: str  # path to the .ace file


@dataclass
class MatchedCode:
    name: str
    present_in: set[str] = field(default_factory=set)  # set of coder IDs


@dataclass
class MatchedAnnotation:
    source_hash: str  # content_hash of the source
    coder_id: str  # CoderInfo.id
    code_name: str  # MatchedCode.name
    start_offset: int
    end_offset: int


@dataclass
class AgreementDataset:
    sources: list[MatchedSource]
    coders: list[CoderInfo]
    codes: list[MatchedCode]
    annotations: list[MatchedAnnotation]
    warnings: list[str]


@dataclass
class CodeMetrics:
    percent_agreement: float
    n_positions: int
    cohens_kappa: float | None = None
    krippendorffs_alpha: float | None = None
    fleiss_kappa: float | None = None
    congers_kappa: float | None = None
    gwets_ac1: float | None = None
    brennan_prediger: float | None = None


@dataclass
class AgreementResult:
    overall: CodeMetrics
    per_code: dict[str, CodeMetrics]  # code_name -> metrics
    per_source: dict[str, CodeMetrics]  # display_id -> metrics
    pairwise: dict[tuple[str, str], float]  # (coder_id, coder_id) -> alpha
    n_coders: int
    n_sources: int
    n_codes: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_services/test_agreement_types.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ace/services/agreement_types.py tests/test_services/test_agreement_types.py
git commit -m "feat(agreement): add data structures for agreement computation"
```

---

### Task 3: AgreementLoader — File Validation

**Files:**
- Create: `src/ace/services/agreement_loader.py`
- Create: `tests/test_services/test_agreement_loader.py`

This task covers opening `.ace` files read-only, validating them, and extracting basic metadata (coder names, source counts).

- [ ] **Step 1: Write test for valid .ace file loading**

```python
"""Tests for AgreementLoader."""

import sqlite3
from pathlib import Path

from ace.db.connection import create_project
from ace.db.schema import ACE_APPLICATION_ID
from ace.models.source import add_source
from ace.models.codebook import add_code
from ace.models.annotation import add_annotation
from ace.models.coder import add_coder
from ace.services.agreement_loader import AgreementLoader


def _make_coder_file(path: Path, coder_name: str, text: str, code_name: str, spans: list[tuple[int, int]]) -> Path:
    """Helper: create an .ace file with one coder, one source, one code, N annotations."""
    conn = create_project(path, f"Project {coder_name}")
    source_id = add_source(conn, "S001", text, "row")
    code_id = add_code(conn, code_name, "#4CAF50")

    # Rename the default coder
    conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", (coder_name,))
    conn.commit()
    coder_id = conn.execute("SELECT id FROM coder WHERE name = ?", (coder_name,)).fetchone()["id"]

    for start, end in spans:
        add_annotation(conn, source_id, coder_id, code_id, start, end, text[start:end])

    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()
    return path


def test_load_single_valid_file(tmp_path):
    text = "I enjoyed the group work sessions."
    path = _make_coder_file(tmp_path / "alice.ace", "Alice", text, "Positive", [(2, 9)])

    loader = AgreementLoader()
    info = loader.add_file(path)

    assert info["coder_names"] == ["Alice"]
    assert info["source_count"] == 1
    assert info["annotation_count"] == 1
    assert info["warnings"] == []


def test_reject_invalid_file(tmp_path):
    bad_file = tmp_path / "bad.ace"
    conn = sqlite3.connect(str(bad_file))
    conn.execute("CREATE TABLE dummy (id TEXT)")
    conn.close()

    loader = AgreementLoader()
    info = loader.add_file(bad_file)
    assert info["error"] is not None
    assert "not a valid ACE project" in info["error"].lower()


def test_warn_wal_file(tmp_path):
    text = "Test text here."
    path = _make_coder_file(tmp_path / "bob.ace", "Bob", text, "Code", [(0, 4)])
    # Create a fake WAL file
    wal_path = Path(str(path) + "-wal")
    wal_path.write_bytes(b"fake wal")

    loader = AgreementLoader()
    info = loader.add_file(path)
    assert any("uncommitted" in w.lower() for w in info["warnings"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_services/test_agreement_loader.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement AgreementLoader file validation**

Create `src/ace/services/agreement_loader.py`:

```python
"""Loads and matches data from multiple .ace files for agreement computation."""

import sqlite3
from pathlib import Path

from ace.db.schema import ACE_APPLICATION_ID
from ace.services.agreement_types import (
    AgreementDataset,
    CoderInfo,
    MatchedAnnotation,
    MatchedCode,
    MatchedSource,
)


class AgreementLoader:
    """Loads multiple .ace files, validates them, extracts and matches data."""

    def __init__(self):
        self._files: list[dict] = []  # metadata per file
        self._file_data: list[dict] = []  # extracted data per file

    @property
    def file_count(self) -> int:
        return len(self._files)

    def add_file(self, path: Path | str) -> dict:
        """Add an .ace file. Returns metadata dict with coder_names, source_count, etc.

        On error, returns dict with 'error' key.
        """
        path = Path(path)
        warnings: list[str] = []

        # Check WAL file
        wal_path = Path(str(path) + "-wal")
        if wal_path.exists():
            warnings.append(
                f"'{path.name}' may have uncommitted changes. "
                "Close ACE on this file first."
            )

        # Open read-only
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
        except sqlite3.OperationalError as e:
            return {"error": f"Cannot open '{path.name}': {e}"}

        try:
            # Validate application_id
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            if app_id != ACE_APPLICATION_ID:
                return {
                    "error": f"'{path.name}' is not a valid ACE project file."
                }

            # Extract metadata
            coders = conn.execute("SELECT id, name FROM coder").fetchall()
            coder_names = [c["name"] for c in coders]

            source_count = conn.execute(
                "SELECT COUNT(*) FROM source"
            ).fetchone()[0]

            annotation_count = conn.execute(
                "SELECT COUNT(*) FROM annotation WHERE deleted_at IS NULL"
            ).fetchone()[0]

            if annotation_count == 0:
                return {
                    "error": f"'{path.name}' has no annotations."
                }

            # Extract full data for matching
            file_data = self._extract_file_data(conn, path)
            self._file_data.append(file_data)

            info = {
                "path": str(path),
                "filename": path.name,
                "coder_names": coder_names,
                "source_count": source_count,
                "annotation_count": annotation_count,
                "warnings": warnings,
                "error": None,
            }
            self._files.append(info)
            return info

        finally:
            conn.close()

    def _extract_file_data(self, conn: sqlite3.Connection, path: Path) -> dict:
        """Extract sources, codes, coders, annotations from a single file."""
        # Project metadata
        project = conn.execute("SELECT codebook_hash FROM project").fetchone()
        codebook_hash = project["codebook_hash"] if project else None

        # Sources with content
        sources = conn.execute(
            "SELECT s.id, s.display_id, sc.content_text, sc.content_hash "
            "FROM source s JOIN source_content sc ON s.id = sc.source_id"
        ).fetchall()

        # Codes
        codes = conn.execute(
            "SELECT id, name FROM codebook_code ORDER BY sort_order"
        ).fetchall()

        # Coders
        coders = conn.execute("SELECT id, name FROM coder").fetchall()

        # Annotations (non-deleted)
        annotations = conn.execute(
            "SELECT a.source_id, a.coder_id, a.code_id, a.start_offset, a.end_offset "
            "FROM annotation a WHERE a.deleted_at IS NULL"
        ).fetchall()

        # Build lookup maps
        source_map = {s["id"]: dict(s) for s in sources}
        code_map = {c["id"]: c["name"] for c in codes}
        coder_map = {c["id"]: c["name"] for c in coders}

        return {
            "path": str(path),
            "codebook_hash": codebook_hash,
            "sources": source_map,
            "codes": code_map,
            "coders": coder_map,
            "annotations": [dict(a) for a in annotations],
        }

    def validate(self) -> dict:
        """Cross-file validation. Returns summary with matched/unmatched counts and warnings."""
        warnings: list[str] = []

        if len(self._file_data) < 2:
            return {
                "valid": False,
                "error": "Add at least one more coder file.",
                "warnings": warnings,
            }

        # Match sources by content_hash
        hash_sets = [
            {s["content_hash"] for s in fd["sources"].values()}
            for fd in self._file_data
        ]
        common_hashes = hash_sets[0]
        for hs in hash_sets[1:]:
            common_hashes = common_hashes & hs

        all_hashes = set()
        for hs in hash_sets:
            all_hashes |= hs

        if not common_hashes:
            return {
                "valid": False,
                "error": "These files share no source texts. Are they from the same project?",
                "warnings": warnings,
            }

        partial = len(all_hashes) - len(common_hashes)
        if partial > 0:
            warnings.append(
                f"{len(common_hashes)} of {len(all_hashes)} sources match. "
                "Agreement will be computed on matched sources only."
            )

        # Match codes by name (or fast-path via codebook_hash)
        codebook_hashes = [fd["codebook_hash"] for fd in self._file_data]
        fast_path = all(h == codebook_hashes[0] and h is not None for h in codebook_hashes)

        if fast_path:
            # All codebooks identical — use names from first file
            common_code_names = set(self._file_data[0]["codes"].values())
        else:
            name_sets = [set(fd["codes"].values()) for fd in self._file_data]
            common_code_names = name_sets[0]
            for ns in name_sets[1:]:
                common_code_names = common_code_names & ns

            all_code_names = set()
            for ns in name_sets:
                all_code_names |= ns

            if not common_code_names:
                return {
                    "valid": False,
                    "error": "These files share no codes. Agreement cannot be computed.",
                    "warnings": warnings,
                }

            unmatched = len(all_code_names) - len(common_code_names)
            if unmatched > 0:
                warnings.append(
                    f"{len(common_code_names)} of {len(all_code_names)} codes match. "
                    "Unmatched codes will be excluded."
                )

        # Identify coders
        coder_labels = self._resolve_coder_labels()

        return {
            "valid": True,
            "error": None,
            "matched_sources": len(common_hashes),
            "matched_codes": len(common_code_names),
            "coders": [c.label for c in coder_labels],
            "n_coders": len(coder_labels),
            "warnings": warnings,
        }

    def _resolve_coder_labels(self) -> list[CoderInfo]:
        """Build unique coder identities from all files."""
        coders: list[CoderInfo] = []
        seen_names: dict[str, int] = {}

        for i, fd in enumerate(self._file_data):
            path = fd["path"]
            filename = Path(path).stem
            for coder_id, coder_name in fd["coders"].items():
                # Check for ambiguous names
                if coder_name in seen_names or coder_name == "default":
                    label = f"{coder_name} ({filename})"
                else:
                    label = coder_name
                seen_names[coder_name] = seen_names.get(coder_name, 0) + 1
                unique_id = f"{i}_{coder_id}"
                coders.append(CoderInfo(id=unique_id, label=label, source_file=path))

        # Second pass: if any name appeared more than once, relabel all instances
        name_counts = {}
        for c in coders:
            base = c.label.split(" (")[0]
            name_counts[base] = name_counts.get(base, 0) + 1

        counters: dict[str, int] = {}
        for c in coders:
            base = c.label.split(" (")[0]
            if name_counts[base] > 1 and base != c.label:
                pass  # already disambiguated with filename
            elif name_counts[base] > 1:
                counters[base] = counters.get(base, 0) + 1
                c.label = f"{base} ({Path(c.source_file).stem})"

        return coders

    def build_dataset(self) -> AgreementDataset:
        """Build the unified AgreementDataset from all loaded files.

        Call validate() first to ensure data is valid.
        """
        validation = self.validate()
        if not validation["valid"]:
            raise ValueError(validation["error"])

        # Resolve coders
        coders = self._resolve_coder_labels()

        # Build source lookup: content_hash -> MatchedSource
        # Use intersection of content_hashes across all files
        hash_sets = [
            {s["content_hash"] for s in fd["sources"].values()}
            for fd in self._file_data
        ]
        common_hashes = hash_sets[0]
        for hs in hash_sets[1:]:
            common_hashes = common_hashes & hs

        # Pick display_id and content_text from the first file that has each hash
        sources: list[MatchedSource] = []
        hash_to_source: dict[str, MatchedSource] = {}
        for fd in self._file_data:
            for src in fd["sources"].values():
                h = src["content_hash"]
                if h in common_hashes and h not in hash_to_source:
                    ms = MatchedSource(
                        content_hash=h,
                        display_id=src["display_id"],
                        content_text=src["content_text"],
                    )
                    hash_to_source[h] = ms
                    sources.append(ms)

        # Match codes
        codebook_hashes = [fd["codebook_hash"] for fd in self._file_data]
        fast_path = all(h == codebook_hashes[0] and h is not None for h in codebook_hashes)

        if fast_path:
            common_code_names = set(self._file_data[0]["codes"].values())
        else:
            name_sets = [set(fd["codes"].values()) for fd in self._file_data]
            common_code_names = name_sets[0]
            for ns in name_sets[1:]:
                common_code_names = common_code_names & ns

        codes = [MatchedCode(name=n) for n in sorted(common_code_names)]
        code_name_set = common_code_names

        # Build annotations
        annotations: list[MatchedAnnotation] = []
        for i, fd in enumerate(self._file_data):
            # Build reverse lookups for this file
            source_id_to_hash = {
                sid: s["content_hash"] for sid, s in fd["sources"].items()
            }
            code_id_to_name = fd["codes"]

            for ann in fd["annotations"]:
                source_hash = source_id_to_hash.get(ann["source_id"])
                code_name = code_id_to_name.get(ann["code_id"])

                # Skip if source not in common set or code not matched
                if source_hash not in common_hashes:
                    continue
                if code_name not in code_name_set:
                    continue

                coder_unique_id = f"{i}_{ann['coder_id']}"
                annotations.append(
                    MatchedAnnotation(
                        source_hash=source_hash,
                        coder_id=coder_unique_id,
                        code_name=code_name,
                        start_offset=ann["start_offset"],
                        end_offset=ann["end_offset"],
                    )
                )

        # Update codes with present_in
        coder_codes: dict[str, set[str]] = {c.name: set() for c in codes}
        for ann in annotations:
            if ann.code_name in coder_codes:
                coder_codes[ann.code_name].add(ann.coder_id)
        for code in codes:
            code.present_in = coder_codes[code.name]

        # Collect all warnings
        all_warnings = list(validation.get("warnings", []))
        for f in self._files:
            all_warnings.extend(f.get("warnings", []))

        return AgreementDataset(
            sources=sources,
            coders=coders,
            codes=codes,
            annotations=annotations,
            warnings=all_warnings,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_services/test_agreement_loader.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Write tests for cross-file matching and validation**

Add to `tests/test_services/test_agreement_loader.py`:

```python
def test_validate_two_matching_files(tmp_path):
    text = "I enjoyed the group work sessions."
    _make_coder_file(tmp_path / "alice.ace", "Alice", text, "Positive", [(2, 9)])
    _make_coder_file(tmp_path / "bob.ace", "Bob", text, "Positive", [(2, 12)])

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    result = loader.validate()
    assert result["valid"] is True
    assert result["matched_sources"] == 1
    assert result["matched_codes"] == 1
    assert result["n_coders"] == 2


def test_validate_no_overlapping_sources(tmp_path):
    _make_coder_file(tmp_path / "alice.ace", "Alice", "Text A", "Code", [(0, 4)])
    _make_coder_file(tmp_path / "bob.ace", "Bob", "Text B", "Code", [(0, 4)])

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    result = loader.validate()
    assert result["valid"] is False
    assert "no source texts" in result["error"].lower()


def test_validate_no_shared_codes(tmp_path):
    text = "Same text for both."
    _make_coder_file(tmp_path / "alice.ace", "Alice", text, "CodeA", [(0, 4)])
    _make_coder_file(tmp_path / "bob.ace", "Bob", text, "CodeB", [(0, 4)])

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    result = loader.validate()
    assert result["valid"] is False
    assert "no codes" in result["error"].lower()


def test_build_dataset(tmp_path):
    text = "I enjoyed the group work sessions."
    _make_coder_file(tmp_path / "alice.ace", "Alice", text, "Positive", [(2, 9)])
    _make_coder_file(tmp_path / "bob.ace", "Bob", text, "Positive", [(2, 12)])

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    ds = loader.build_dataset()
    assert len(ds.sources) == 1
    assert len(ds.coders) == 2
    assert len(ds.codes) == 1
    assert ds.codes[0].name == "Positive"
    assert len(ds.annotations) == 2
    assert ds.sources[0].content_text == text
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_services/test_agreement_loader.py -v`
Expected: All 7 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/ace/services/agreement_loader.py tests/test_services/test_agreement_loader.py
git commit -m "feat(agreement): add AgreementLoader with file validation and cross-file matching"
```

---

## Chunk 2: AgreementComputer — All Metrics

### Task 4: AgreementComputer — Core Metrics (Percent Agreement + Cohen's Kappa)

**Files:**
- Create: `src/ace/services/agreement_computer.py`
- Create: `tests/test_services/test_agreement_computer.py`

- [ ] **Step 1: Write test for perfect agreement**

```python
"""Tests for AgreementComputer."""

from ace.services.agreement_types import (
    AgreementDataset,
    CoderInfo,
    MatchedAnnotation,
    MatchedCode,
    MatchedSource,
)
from ace.services.agreement_computer import compute_agreement


def _make_dataset(annotations: list[MatchedAnnotation], n_coders=2) -> AgreementDataset:
    """Helper to build a minimal dataset."""
    coders = [CoderInfo(id=f"c{i}", label=f"Coder {i}", source_file=f"f{i}.ace") for i in range(n_coders)]
    return AgreementDataset(
        sources=[MatchedSource(
            content_hash="hash1",
            display_id="S001",
            content_text="I enjoyed the group work but lectures were too fast",
        )],
        coders=coders,
        codes=[MatchedCode(name="Positive", present_in={"c0", "c1"})],
        annotations=annotations,
        warnings=[],
    )


def test_perfect_agreement():
    """Both coders annotate the exact same span."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=28),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=28),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)

    assert result.overall.percent_agreement > 0.99
    assert result.overall.cohens_kappa is not None
    assert result.overall.cohens_kappa > 0.9
    assert result.n_coders == 2
    assert result.n_sources == 1
    assert "Positive" in result.per_code


def test_no_agreement():
    """Coders annotate completely different spans with the same code."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=10),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=30, end_offset=40),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)

    assert result.overall.percent_agreement < 0.5
    assert result.overall.cohens_kappa is not None
    assert result.overall.cohens_kappa < 0.1


def test_empty_annotations():
    """Dataset with no annotations produces zero metrics."""
    ds = _make_dataset([])
    result = compute_agreement(ds)
    assert result.overall.percent_agreement == 0.0
    assert result.overall.n_positions == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_services/test_agreement_computer.py::test_perfect_agreement -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement core computation**

Create `src/ace/services/agreement_computer.py`:

```python
"""Computes inter-coder agreement metrics from an AgreementDataset."""

import math
from collections import defaultdict

import krippendorff
import numpy as np
import pandas as pd
from irrCAC.raw import CAC
from sklearn.metrics import cohen_kappa_score

from ace.services.agreement_types import (
    AgreementDataset,
    AgreementResult,
    CodeMetrics,
)


def compute_agreement(dataset: AgreementDataset) -> AgreementResult:
    """Compute all agreement metrics from a matched dataset."""
    if not dataset.annotations or not dataset.sources or not dataset.codes:
        empty = CodeMetrics(percent_agreement=0.0, n_positions=0)
        return AgreementResult(
            overall=empty,
            per_code={},
            per_source={},
            pairwise={},
            n_coders=len(dataset.coders),
            n_sources=0,
            n_codes=0,
        )

    coder_ids = [c.id for c in dataset.coders]
    code_names = [c.name for c in dataset.codes]

    # Group annotations by (source_hash, coder_id, code_name)
    ann_index = defaultdict(list)
    for ann in dataset.annotations:
        ann_index[(ann.source_hash, ann.coder_id, ann.code_name)].append(ann)

    # Build character-level vectors per code, aggregated across sources
    per_code_vectors: dict[str, dict[str, list[int]]] = {
        cn: {cid: [] for cid in coder_ids} for cn in code_names
    }

    # Also per source
    per_source_vectors: dict[str, dict[str, list[int]]] = {}

    for source in dataset.sources:
        text_len = len(source.content_text)
        if text_len == 0:
            continue

        # Track which positions have any code applied by any coder
        any_coded = [0] * text_len

        # Build vectors per code per coder for this source
        source_code_vecs: dict[str, dict[str, list[int]]] = {}
        for cn in code_names:
            vecs = {}
            for cid in coder_ids:
                vec = [0] * text_len
                for ann in ann_index.get((source.content_hash, cid, cn), []):
                    for i in range(ann.start_offset, min(ann.end_offset, text_len)):
                        vec[i] = 1
                        any_coded[i] = 1
                vecs[cid] = vec
            source_code_vecs[cn] = vecs

        # Filter to positions where at least one coder applied at least one code
        coded_positions = [i for i in range(text_len) if any_coded[i]]
        if not coded_positions:
            continue

        # Aggregate into per-code vectors
        for cn in code_names:
            for cid in coder_ids:
                vec = source_code_vecs[cn][cid]
                for pos in coded_positions:
                    per_code_vectors[cn][cid].append(vec[pos])

        # Aggregate into per-source vectors (all codes flattened)
        source_key = source.display_id
        if source_key not in per_source_vectors:
            per_source_vectors[source_key] = {cid: [] for cid in coder_ids}
        for cn in code_names:
            for cid in coder_ids:
                vec = source_code_vecs[cn][cid]
                for pos in coded_positions:
                    per_source_vectors[source_key][cid].append(vec[pos])

    # Compute per-code metrics
    per_code_results: dict[str, CodeMetrics] = {}
    for cn in code_names:
        vectors = per_code_vectors[cn]
        per_code_results[cn] = _compute_metrics(vectors, coder_ids)

    # Compute per-source metrics
    per_source_results: dict[str, CodeMetrics] = {}
    for src_key, vectors in per_source_vectors.items():
        per_source_results[src_key] = _compute_metrics(vectors, coder_ids)

    # Compute overall (macro-average of per-code)
    overall = _macro_average(list(per_code_results.values()))

    # Compute pairwise alpha
    pairwise = _compute_pairwise(per_code_vectors, coder_ids)

    return AgreementResult(
        overall=overall,
        per_code=per_code_results,
        per_source=per_source_results,
        pairwise=pairwise,
        n_coders=len(dataset.coders),
        n_sources=len(per_source_vectors),
        n_codes=len(code_names),
    )


def _compute_metrics(vectors: dict[str, list[int]], coder_ids: list[str]) -> CodeMetrics:
    """Compute all metrics from coder vectors."""
    # Check we have data
    vec_len = len(vectors[coder_ids[0]]) if coder_ids else 0
    if vec_len == 0:
        return CodeMetrics(percent_agreement=0.0, n_positions=0)

    n_coders = len(coder_ids)

    # Percent agreement (pairwise average)
    pair_agrees = []
    for i in range(n_coders):
        for j in range(i + 1, n_coders):
            v1 = vectors[coder_ids[i]]
            v2 = vectors[coder_ids[j]]
            agree = sum(1 for a, b in zip(v1, v2) if a == b) / vec_len
            pair_agrees.append(agree)
    pct_agree = sum(pair_agrees) / len(pair_agrees) if pair_agrees else 0.0

    # Cohen's kappa (only for 2 coders)
    cohens_k = None
    if n_coders == 2:
        cohens_k = _safe_kappa(vectors[coder_ids[0]], vectors[coder_ids[1]])

    # Krippendorff's alpha
    k_alpha = _safe_krippendorff(vectors, coder_ids)

    # irrCAC metrics (Fleiss, Conger, Gwet, Brennan-Prediger)
    fleiss_k, congers_k, gwets, bp = _compute_irrcac(vectors, coder_ids)

    return CodeMetrics(
        percent_agreement=pct_agree,
        n_positions=vec_len,
        cohens_kappa=cohens_k,
        krippendorffs_alpha=k_alpha,
        fleiss_kappa=fleiss_k,
        congers_kappa=congers_k,
        gwets_ac1=gwets,
        brennan_prediger=bp,
    )


def _safe_kappa(vec1: list[int], vec2: list[int]) -> float | None:
    """Cohen's kappa with edge case handling."""
    try:
        k = cohen_kappa_score(vec1, vec2)
        if math.isnan(k):
            return 1.0 if vec1 == vec2 else None
        return k
    except ValueError:
        return 1.0 if vec1 == vec2 else None


def _safe_krippendorff(vectors: dict[str, list[int]], coder_ids: list[str]) -> float | None:
    """Krippendorff's alpha with edge case handling."""
    try:
        # krippendorff expects a reliability data matrix: raters x units
        matrix = np.array([vectors[cid] for cid in coder_ids])
        alpha = krippendorff.alpha(
            reliability_data=matrix, level_of_measurement="nominal"
        )
        if math.isnan(alpha):
            return None
        return float(alpha)
    except Exception:
        return None


def _compute_irrcac(
    vectors: dict[str, list[int]], coder_ids: list[str]
) -> tuple[float | None, float | None, float | None, float | None]:
    """Compute Fleiss, Conger, Gwet AC1, Brennan-Prediger via irrCAC."""
    try:
        # irrCAC expects a DataFrame: subjects x raters
        df = pd.DataFrame({cid: vectors[cid] for cid in coder_ids})
        cac = CAC(df)

        fleiss = _extract_coeff(cac.fleiss())
        conger = _extract_coeff(cac.conger())
        gwet = _extract_coeff(cac.gwet())
        bp = _extract_coeff(cac.bp())

        return fleiss, conger, gwet, bp
    except Exception:
        return None, None, None, None


def _extract_coeff(result) -> float | None:
    """Extract coefficient value from an irrCAC result."""
    try:
        coeff = result["est"]["coefficient_value"]
        if isinstance(coeff, pd.Series):
            coeff = coeff.iloc[0]
        if math.isnan(float(coeff)):
            return None
        return float(coeff)
    except (KeyError, TypeError, IndexError):
        return None


def _macro_average(metrics_list: list[CodeMetrics]) -> CodeMetrics:
    """Macro-average across a list of CodeMetrics."""
    if not metrics_list:
        return CodeMetrics(percent_agreement=0.0, n_positions=0)

    def avg(vals: list[float | None]) -> float | None:
        nums = [v for v in vals if v is not None]
        return sum(nums) / len(nums) if nums else None

    total_positions = sum(m.n_positions for m in metrics_list)
    pct = avg([m.percent_agreement for m in metrics_list if m.n_positions > 0])

    return CodeMetrics(
        percent_agreement=pct or 0.0,
        n_positions=total_positions,
        cohens_kappa=avg([m.cohens_kappa for m in metrics_list]),
        krippendorffs_alpha=avg([m.krippendorffs_alpha for m in metrics_list]),
        fleiss_kappa=avg([m.fleiss_kappa for m in metrics_list]),
        congers_kappa=avg([m.congers_kappa for m in metrics_list]),
        gwets_ac1=avg([m.gwets_ac1 for m in metrics_list]),
        brennan_prediger=avg([m.brennan_prediger for m in metrics_list]),
    )


def _compute_pairwise(
    per_code_vectors: dict[str, dict[str, list[int]]],
    coder_ids: list[str],
) -> dict[tuple[str, str], float]:
    """Compute pairwise Krippendorff's alpha between each coder pair."""
    pairwise: dict[tuple[str, str], float] = {}

    for i in range(len(coder_ids)):
        for j in range(i + 1, len(coder_ids)):
            cid_i, cid_j = coder_ids[i], coder_ids[j]
            # Concatenate all code vectors for this pair
            pair_vecs = {cid_i: [], cid_j: []}
            for cn in per_code_vectors:
                pair_vecs[cid_i].extend(per_code_vectors[cn][cid_i])
                pair_vecs[cid_j].extend(per_code_vectors[cn][cid_j])

            alpha = _safe_krippendorff(pair_vecs, [cid_i, cid_j])
            if alpha is not None:
                pairwise[(cid_i, cid_j)] = alpha

    return pairwise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_services/test_agreement_computer.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Write tests for all metric types and multi-code scenarios**

Add to `tests/test_services/test_agreement_computer.py`:

```python
def test_krippendorff_alpha_computed():
    """Verify Krippendorff's alpha is computed."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=28),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=28),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)
    assert result.overall.krippendorffs_alpha is not None


def test_irrcac_metrics_computed():
    """Verify irrCAC metrics are computed for 2+ coders."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=28),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=28),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)
    # For 2 coders, Fleiss' kappa should still compute (it generalises)
    assert result.overall.gwets_ac1 is not None
    assert result.overall.brennan_prediger is not None


def test_per_source_metrics():
    """Verify per-source metrics are computed."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=10),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=10),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)
    assert "S001" in result.per_source
    assert result.per_source["S001"].percent_agreement > 0.9


def test_pairwise_alpha():
    """Verify pairwise alpha is computed."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=28),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=28),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)
    assert len(result.pairwise) == 1  # one pair for 2 coders
    pair_key = list(result.pairwise.keys())[0]
    assert result.pairwise[pair_key] > 0.9


def test_multi_code_dataset():
    """Two codes, partial agreement."""
    ds = AgreementDataset(
        sources=[MatchedSource(
            content_hash="hash1",
            display_id="S001",
            content_text="I enjoyed the group work but lectures were too fast",
        )],
        coders=[
            CoderInfo(id="c0", label="Alice", source_file="a.ace"),
            CoderInfo(id="c1", label="Bob", source_file="b.ace"),
        ],
        codes=[
            MatchedCode(name="Positive", present_in={"c0", "c1"}),
            MatchedCode(name="Negative", present_in={"c0", "c1"}),
        ],
        annotations=[
            # Both agree on Positive span
            MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=28),
            MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=28),
            # Only Alice applies Negative
            MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Negative", start_offset=33, end_offset=51),
        ],
        warnings=[],
    )
    result = compute_agreement(ds)
    assert result.per_code["Positive"].percent_agreement > result.per_code["Negative"].percent_agreement
    assert result.n_codes == 2
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/test_services/test_agreement_computer.py -v`
Expected: All 8 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/ace/services/agreement_computer.py tests/test_services/test_agreement_computer.py
git commit -m "feat(agreement): add AgreementComputer with all metrics"
```

---

## Chunk 3: Integration — End-to-End Loader + Computer

### Task 5: End-to-End Test

**Files:**
- Create: `tests/test_services/test_agreement_e2e.py`

- [ ] **Step 1: Write end-to-end test**

```python
"""End-to-end tests: AgreementLoader -> AgreementComputer."""

from pathlib import Path

from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.coder import add_coder
from ace.models.source import add_source
from ace.services.agreement_computer import compute_agreement
from ace.services.agreement_loader import AgreementLoader


def _make_coder_file(
    path: Path,
    coder_name: str,
    sources: list[tuple[str, str]],
    code_name: str,
    annotations: list[tuple[int, int, int, int]],
) -> Path:
    """Create an .ace file.

    sources: list of (display_id, text)
    annotations: list of (source_index, code_index_unused, start, end)
    """
    conn = create_project(path, f"Project {coder_name}")

    source_ids = []
    for display_id, text in sources:
        sid = add_source(conn, display_id, text, "row")
        source_ids.append(sid)

    code_id = add_code(conn, code_name, "#4CAF50")

    conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", (coder_name,))
    conn.commit()
    coder_id = conn.execute(
        "SELECT id FROM coder WHERE name = ?", (coder_name,)
    ).fetchone()["id"]

    for src_idx, _, start, end in annotations:
        sid = source_ids[src_idx]
        text = sources[src_idx][1]
        add_annotation(conn, sid, coder_id, code_id, start, end, text[start:end])

    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()
    return path


def test_e2e_two_coders_perfect_agreement(tmp_path):
    sources = [("S001", "I enjoyed the group work but lectures were too fast")]
    _make_coder_file(
        tmp_path / "alice.ace", "Alice", sources, "Positive",
        [(0, 0, 2, 28)],
    )
    _make_coder_file(
        tmp_path / "bob.ace", "Bob", sources, "Positive",
        [(0, 0, 2, 28)],
    )

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    ds = loader.build_dataset()
    result = compute_agreement(ds)

    assert result.n_coders == 2
    assert result.n_sources == 1
    assert result.overall.percent_agreement > 0.99
    assert result.overall.cohens_kappa is not None
    assert result.overall.cohens_kappa > 0.9
    assert result.overall.krippendorffs_alpha is not None


def test_e2e_three_coders(tmp_path):
    sources = [("S001", "I enjoyed the group work but lectures were too fast")]
    _make_coder_file(
        tmp_path / "alice.ace", "Alice", sources, "Positive",
        [(0, 0, 2, 28)],
    )
    _make_coder_file(
        tmp_path / "bob.ace", "Bob", sources, "Positive",
        [(0, 0, 2, 28)],
    )
    _make_coder_file(
        tmp_path / "carol.ace", "Carol", sources, "Positive",
        [(0, 0, 2, 28)],
    )

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")
    loader.add_file(tmp_path / "carol.ace")

    ds = loader.build_dataset()
    result = compute_agreement(ds)

    assert result.n_coders == 3
    assert result.overall.fleiss_kappa is not None
    assert len(result.pairwise) == 3  # 3 pairs for 3 coders


def test_e2e_multiple_sources(tmp_path):
    sources = [
        ("S001", "I enjoyed the group work sessions."),
        ("S002", "The lectures were too fast-paced."),
    ]
    _make_coder_file(
        tmp_path / "alice.ace", "Alice", sources, "Positive",
        [(0, 0, 2, 9), (1, 0, 4, 12)],
    )
    _make_coder_file(
        tmp_path / "bob.ace", "Bob", sources, "Positive",
        [(0, 0, 2, 9), (1, 0, 4, 15)],
    )

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    ds = loader.build_dataset()
    result = compute_agreement(ds)

    assert result.n_sources == 2
    assert len(result.per_source) == 2
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_services/test_agreement_e2e.py -v`
Expected: All 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_services/test_agreement_e2e.py
git commit -m "test(agreement): add end-to-end loader + computer integration tests"
```

---

## Chunk 4: CSS + Page Route + Landing Page Button

### Task 6: CSS Classes

**Files:**
- Modify: `src/ace/static/css/theme.css`
- Create: `src/ace/static/css/agreement.css`

- [ ] **Step 1: Add ace-metric classes to theme.css**

Append to the end of `src/ace/static/css/theme.css`:

```css
/* Agreement dashboard metric typography */
.ace-metric {
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    font-size: 0.875rem;
}
.ace-metric-hero {
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    font-size: 2.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
}
```

- [ ] **Step 2: Create agreement.css with heatmap styles**

Create `src/ace/static/css/agreement.css`:

```css
/* Agreement dashboard styles */
.ace-heatmap {
    border-collapse: collapse;
    width: 100%;
    max-width: 600px;
}
.ace-heatmap th,
.ace-heatmap td {
    border: 1px solid #d0d0d0;
    padding: 8px 12px;
    text-align: center;
    font-size: 0.875rem;
}
.ace-heatmap th {
    background: #f5f5f5;
    font-weight: 500;
    color: #616161;
}
.ace-heatmap td.ace-low-agreement {
    border: 2px dashed #bdbdbd;
}
```

- [ ] **Step 3: Commit**

```bash
git add src/ace/static/css/theme.css src/ace/static/css/agreement.css
git commit -m "style: add agreement dashboard CSS classes"
```

---

### Task 7: Agreement Page Route + Landing Page Button

**Files:**
- Create: `src/ace/pages/agreement.py`
- Modify: `src/ace/pages/landing.py`
- Modify: `src/ace/app.py`

- [ ] **Step 1: Create minimal agreement page with empty state**

Create `src/ace/pages/agreement.py`:

```python
"""Agreement dashboard page — /agreement route."""

import platform
import subprocess
from pathlib import Path

from nicegui import ui

from ace.pages.header import build_header
from ace.services.agreement_loader import AgreementLoader


def register():
    @ui.page("/agreement")
    async def agreement_page():
        build_header()
        ui.add_css((Path(__file__).parent.parent / "static" / "css" / "agreement.css").read_text())

        loader = AgreementLoader()
        file_list_container = ui.column()
        validation_container = ui.column()
        results_container = ui.column().classes("full-width")

        with ui.column().classes("mx-auto q-pa-lg").style("max-width: 1100px; width: 100%;"):
            # Setup area
            with ui.column().classes("full-width q-mb-lg"):
                ui.label("Inter-Coder Agreement").classes("text-h5 text-weight-medium")

                # Empty state
                with ui.column().classes("items-center q-pa-xl full-width") as empty_state:
                    ui.icon("compare_arrows", size="48px", color="grey-4")
                    ui.label("Compare Coder Annotations").classes(
                        "text-h6 text-grey-5 q-mt-sm"
                    )
                    ui.label(
                        "Add two or more .ace project files to compare annotations "
                        "and compute agreement metrics."
                    ).classes("text-body2 text-grey-6").style(
                        "max-width: 400px; text-align: center;"
                    )

                # File controls
                with ui.row().classes("items-center gap-2 q-mt-md"):
                    ui.button(
                        "Add File", icon="add", on_click=lambda: _pick_and_add_file(loader, file_list_container, validation_container, compute_btn, empty_state)
                    ).props("flat dense no-caps").classes("text-grey-8")

                file_list_container.move(target_index=-1)
                validation_container.move(target_index=-1)

                compute_btn = ui.button(
                    "Compute Agreement",
                    icon="calculate",
                    on_click=lambda: _run_computation(loader, results_container),
                ).props("no-caps").classes("q-mt-md")
                compute_btn.set_visibility(False)

            results_container.move(target_index=-1)


_IS_MACOS = platform.system() == "Darwin"


async def _pick_and_add_file(loader, file_list_container, validation_container, compute_btn, empty_state):
    """Open native file picker and add the selected .ace file."""
    if _IS_MACOS:
        path = await _native_pick_files()
    else:
        ui.notify("File picker not yet supported on this platform.", type="warning")
        return

    if not path:
        return

    for p in path:
        info = loader.add_file(Path(p))

        if info.get("error"):
            ui.notify(info["error"], type="negative")
            continue

        for w in info.get("warnings", []):
            ui.notify(w, type="warning")

        with file_list_container:
            with ui.row().classes("items-center gap-2 q-pa-sm").style(
                "border: 1px solid #d0d0d0; border-radius: 0;"
            ):
                ui.icon("description", color="grey-6")
                with ui.column().classes("gap-0"):
                    ui.label(", ".join(info["coder_names"])).classes(
                        "text-subtitle2 text-weight-medium"
                    )
                    ui.label(
                        f"{info['filename']} — {info['source_count']} sources, "
                        f"{info['annotation_count']} annotations"
                    ).classes("text-caption text-grey-6")

    # Update validation
    if loader.file_count >= 2:
        empty_state.set_visibility(False)
        validation = loader.validate()
        validation_container.clear()
        with validation_container:
            for w in validation.get("warnings", []):
                with ui.row().classes("items-center gap-1"):
                    ui.icon("warning", color="orange", size="xs")
                    ui.label(w).classes("text-caption text-orange-8")

            if validation["valid"]:
                with ui.row().classes("items-center gap-1"):
                    ui.icon("check_circle", color="green", size="xs")
                    ui.label(
                        f"{validation['matched_sources']} sources, "
                        f"{validation['matched_codes']} codes matched — "
                        f"Coders: {', '.join(validation['coders'])}"
                    ).classes("text-caption text-green-8")
                compute_btn.set_visibility(True)
            else:
                with ui.row().classes("items-center gap-1"):
                    ui.icon("error", color="red", size="xs")
                    ui.label(validation["error"]).classes("text-caption text-red-8")
                compute_btn.set_visibility(False)
    elif loader.file_count == 1:
        empty_state.set_visibility(False)


async def _run_computation(loader, results_container):
    """Compute agreement metrics and render dashboard."""
    from ace.services.agreement_computer import compute_agreement

    try:
        ds = loader.build_dataset()
    except ValueError as e:
        ui.notify(str(e), type="negative")
        return

    ui.notify("Computing agreement metrics...", type="info")
    result = compute_agreement(ds)

    results_container.clear()
    with results_container:
        _render_dashboard(result, ds)


def _render_dashboard(result, dataset):
    """Render the full agreement dashboard."""
    from ace.services.agreement_types import AgreementResult

    # Tabs
    with ui.tabs().classes("text-grey-7") as tabs:
        overview_tab = ui.tab("Overview")
        if result.n_coders > 2:
            pairwise_tab = ui.tab("Pairwise")
        source_tab = ui.tab("Per Source")

    with ui.tab_panels(tabs, value=overview_tab).classes("full-width"):
        with ui.tab_panel(overview_tab):
            _render_overview(result, dataset)
        if result.n_coders > 2:
            with ui.tab_panel(pairwise_tab):
                _render_pairwise(result, dataset)
        with ui.tab_panel(source_tab):
            _render_per_source(result)


def _render_overview(result, dataset):
    """Render the Overview tab."""
    # Hero card — Krippendorff's alpha
    with ui.card().classes("full-width q-pa-lg").style("border: 1px solid #d0d0d0;"):
        ui.label("Krippendorff's Alpha").classes("text-caption text-grey-6")
        alpha_val = result.overall.krippendorffs_alpha
        alpha_str = f"{alpha_val:.3f}" if alpha_val is not None else "N/A"
        ui.label(alpha_str).classes("ace-metric-hero")
        label = _agreement_label(alpha_val)
        ui.label(label).classes("text-subtitle1 text-grey-7")

    # Secondary cards
    with ui.row().classes("gap-4 q-mt-md full-width"):
        # Kappa card
        with ui.card().classes("col q-pa-md").style("border: 1px solid #d0d0d0;"):
            if result.n_coders == 2:
                ui.label("Cohen's Kappa").classes("text-caption text-grey-6")
                val = result.overall.cohens_kappa
            else:
                ui.label("Fleiss' Kappa").classes("text-caption text-grey-6")
                val = result.overall.fleiss_kappa
            val_str = f"{val:.3f}" if val is not None else "N/A"
            ui.label(val_str).classes("ace-metric text-h5")

        # Percent agreement card
        with ui.card().classes("col q-pa-md").style("border: 1px solid #d0d0d0;"):
            ui.label("Percent Agreement").classes("text-caption text-grey-6")
            pct_str = f"{result.overall.percent_agreement:.1%}"
            ui.label(pct_str).classes("ace-metric text-h5")

    # Metadata
    ui.label(
        f"Computed across {result.n_sources} sources, "
        f"{result.n_codes} codes, {result.n_coders} coders"
    ).classes("text-caption text-grey-6 q-mt-sm")

    # Per-code table
    _render_per_code_table(result, dataset)

    # Methods paragraph button
    ui.button(
        "Copy Methods Paragraph",
        icon="content_copy",
        on_click=lambda: _copy_methods_paragraph(result),
    ).props("flat dense no-caps").classes("text-grey-8 q-mt-md")


def _render_per_code_table(result, dataset):
    """Render the per-code agreement table with toggleable additional metrics."""
    base_columns = [
        {"name": "code", "label": "Code Name", "field": "code", "sortable": True, "align": "left"},
        {"name": "pct", "label": "% Agreement", "field": "pct", "sortable": True},
        {"name": "alpha", "label": "K. Alpha", "field": "alpha", "sortable": True},
        {"name": "kappa", "label": "Kappa", "field": "kappa", "sortable": True},
    ]
    extra_columns = [
        {"name": "ac1", "label": "AC1", "field": "ac1", "sortable": True},
        {"name": "bp", "label": "B-P", "field": "bp", "sortable": True},
        {"name": "conger", "label": "Conger", "field": "conger", "sortable": True},
        {"name": "fleiss", "label": "Fleiss", "field": "fleiss", "sortable": True},
    ]

    rows = []
    for code_name, metrics in result.per_code.items():
        kappa_val = metrics.cohens_kappa if result.n_coders == 2 else metrics.fleiss_kappa
        rows.append({
            "code": code_name,
            "pct": f"{metrics.percent_agreement:.1%}",
            "alpha": f"{metrics.krippendorffs_alpha:.3f}" if metrics.krippendorffs_alpha is not None else "N/A",
            "kappa": f"{kappa_val:.3f}" if kappa_val is not None else "N/A",
            "ac1": f"{metrics.gwets_ac1:.3f}" if metrics.gwets_ac1 is not None else "N/A",
            "bp": f"{metrics.brennan_prediger:.3f}" if metrics.brennan_prediger is not None else "N/A",
            "conger": f"{metrics.congers_kappa:.3f}" if metrics.congers_kappa is not None else "N/A",
            "fleiss": f"{metrics.fleiss_kappa:.3f}" if metrics.fleiss_kappa is not None else "N/A",
            "_low": metrics.krippendorffs_alpha is not None and metrics.krippendorffs_alpha < 0.67,
        })

    table = ui.table(columns=base_columns, rows=rows, row_key="code").props("flat dense").classes("full-width")

    def toggle_columns(show_all: bool):
        if show_all:
            table._props["columns"] = base_columns + extra_columns
        else:
            table._props["columns"] = base_columns
        table.update()

    with ui.row().classes("items-center justify-between full-width q-mt-lg q-mb-sm"):
        ui.label("Agreement by Code").classes("text-h6 text-weight-medium")
        with ui.row().classes("items-center gap-2"):
            ui.switch("Show all metrics", on_change=lambda e: toggle_columns(e.value))
            ui.button(
                "Export CSV",
                icon="download",
                on_click=lambda: _export_per_code_csv(result),
            ).props("flat dense no-caps").classes("text-grey-8")


def _render_pairwise(result, dataset):
    """Render the pairwise heatmap tab."""
    coders = dataset.coders
    n = len(coders)

    # Build matrix
    matrix = [[None] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0
        for j in range(i + 1, n):
            key = (coders[i].id, coders[j].id)
            alt_key = (coders[j].id, coders[i].id)
            val = result.pairwise.get(key) or result.pairwise.get(alt_key)
            matrix[i][j] = val
            matrix[j][i] = val

    # Generate HTML
    html = '<table class="ace-heatmap"><tr><th></th>'
    for c in coders:
        html += f"<th>{c.label}</th>"
    html += "</tr>"

    for i, coder in enumerate(coders):
        html += f"<tr><th>{coder.label}</th>"
        for j in range(n):
            val = matrix[i][j]
            if val is None:
                html += "<td>—</td>"
            else:
                bg = _heatmap_color(val)
                text_color = "#ffffff" if val > 0.6 else "#212121"
                css_class = ' class="ace-low-agreement"' if val < 0.67 else ""
                html += (
                    f'<td style="background-color: {bg}; color: {text_color};"{css_class}>'
                    f"{val:.3f}</td>"
                )
        html += "</tr>"

    html += "</table>"
    ui.html(html, sanitize=False)


def _heatmap_color(value: float) -> str:
    """Interpolate from white (#ffffff) to blue (#1565c0) based on value 0-1."""
    r = int(255 + (21 - 255) * value)
    g = int(255 + (101 - 255) * value)
    b = int(255 + (192 - 255) * value)
    return f"rgb({r},{g},{b})"


def _render_per_source(result):
    """Render the per-source tab."""
    with ui.row().classes("items-center justify-between full-width q-mb-sm"):
        ui.label("Agreement by Source").classes("text-h6 text-weight-medium")
        ui.button(
            "Export CSV",
            icon="download",
            on_click=lambda: _export_per_source_csv(result),
        ).props("flat dense no-caps").classes("text-grey-8")

    columns = [
        {"name": "source", "label": "Source ID", "field": "source", "sortable": True, "align": "left"},
        {"name": "pct", "label": "% Agreement", "field": "pct", "sortable": True},
        {"name": "alpha", "label": "K. Alpha", "field": "alpha", "sortable": True},
        {"name": "kappa", "label": "Kappa", "field": "kappa", "sortable": True},
        {"name": "n_pos", "label": "Positions", "field": "n_pos", "sortable": True},
    ]

    rows = []
    for src_id, metrics in sorted(
        result.per_source.items(),
        key=lambda x: x[1].percent_agreement,
    ):
        kappa_val = metrics.cohens_kappa if result.n_coders == 2 else metrics.fleiss_kappa
        rows.append({
            "source": src_id,
            "pct": f"{metrics.percent_agreement:.1%}",
            "alpha": f"{metrics.krippendorffs_alpha:.3f}" if metrics.krippendorffs_alpha is not None else "N/A",
            "kappa": f"{kappa_val:.3f}" if kappa_val is not None else "N/A",
            "n_pos": metrics.n_positions,
        })

    ui.table(columns=columns, rows=rows, row_key="source").props("flat dense").classes("full-width")


def _agreement_label(value: float | None) -> str:
    """Return verbal agreement label (Landis & Koch scale)."""
    if value is None:
        return ""
    if value < 0.0:
        return "Poor"
    if value <= 0.20:
        return "Slight"
    if value <= 0.40:
        return "Fair"
    if value <= 0.60:
        return "Moderate"
    if value <= 0.80:
        return "Substantial"
    return "Near-Perfect"


async def _copy_methods_paragraph(result):
    """Copy a publication-ready methods paragraph to clipboard."""
    alpha = result.overall.krippendorffs_alpha
    alpha_str = f"{alpha:.2f}" if alpha is not None else "N/A"

    if result.n_coders == 2:
        kappa = result.overall.cohens_kappa
        kappa_label = "Cohen's kappa"
    else:
        kappa = result.overall.fleiss_kappa
        kappa_label = "Fleiss' kappa"
    kappa_str = f"{kappa:.2f}" if kappa is not None else "N/A"

    # Per-code range
    code_kappas = []
    for m in result.per_code.values():
        k = m.cohens_kappa if result.n_coders == 2 else m.fleiss_kappa
        if k is not None:
            code_kappas.append(k)

    range_str = ""
    if code_kappas:
        range_str = (
            f" Per-code agreement ranged from "
            f"\u03BA = {min(code_kappas):.2f} to \u03BA = {max(code_kappas):.2f}."
        )

    para = (
        f"Inter-coder reliability was assessed using Krippendorff's alpha "
        f"(\u03B1 = {alpha_str}) and {kappa_label} "
        f"(\u03BA = {kappa_str}) across {result.n_coders} coders "
        f"and {result.n_sources} source texts.{range_str}"
    )

    import json
    await ui.run_javascript(
        f"navigator.clipboard.writeText({json.dumps(para)})"
    )
    ui.notify("Methods paragraph copied to clipboard", type="positive")


async def _native_pick_files() -> list[str]:
    """Open macOS native file picker for multiple .ace files."""
    import asyncio
    loop = asyncio.get_event_loop()

    def _run_picker():
        return subprocess.run(
            [
                "osascript",
                "-e",
                'set theFiles to choose file of type {"ace"} with prompt "Select .ace files to compare" with multiple selections allowed',
                "-e",
                "set output to {}",
                "-e",
                "repeat with f in theFiles",
                "-e",
                "set end of output to POSIX path of f",
                "-e",
                "end repeat",
                "-e",
                'set AppleScript\'s text item delimiters to "\\n"',
                "-e",
                "return output as text",
            ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        return result

    try:
        result = await loop.run_in_executor(None, _run_picker)
        if result.returncode != 0:
            return []
        paths = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
        return paths
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _export_per_code_csv(result):
    """Export per-code metrics as CSV download."""
    import csv
    import io
    from datetime import date

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "code_name", "n_positions", "percent_agreement",
        "cohens_kappa", "krippendorffs_alpha", "fleiss_kappa",
        "gwets_ac1", "brennan_prediger", "congers_kappa",
    ])
    for code_name, m in sorted(result.per_code.items()):
        writer.writerow([
            code_name, m.n_positions, f"{m.percent_agreement:.4f}",
            f"{m.cohens_kappa:.4f}" if m.cohens_kappa is not None else "",
            f"{m.krippendorffs_alpha:.4f}" if m.krippendorffs_alpha is not None else "",
            f"{m.fleiss_kappa:.4f}" if m.fleiss_kappa is not None else "",
            f"{m.gwets_ac1:.4f}" if m.gwets_ac1 is not None else "",
            f"{m.brennan_prediger:.4f}" if m.brennan_prediger is not None else "",
            f"{m.congers_kappa:.4f}" if m.congers_kappa is not None else "",
        ])

    ui.download(buf.getvalue().encode(), f"agreement_by_code_{date.today()}.csv")


def _export_per_source_csv(result):
    """Export per-source metrics as CSV download."""
    import csv
    import io
    from datetime import date

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "source_display_id", "n_positions", "percent_agreement",
        "krippendorffs_alpha", "kappa",
    ])
    for src_id, m in sorted(result.per_source.items()):
        kappa = m.cohens_kappa if m.cohens_kappa is not None else m.fleiss_kappa
        writer.writerow([
            src_id, m.n_positions, f"{m.percent_agreement:.4f}",
            f"{m.krippendorffs_alpha:.4f}" if m.krippendorffs_alpha is not None else "",
            f"{kappa:.4f}" if kappa is not None else "",
        ])

    ui.download(buf.getvalue().encode(), f"agreement_by_source_{date.today()}.csv")
```

- [ ] **Step 2: Register route in app.py**

In `src/ace/app.py`, add the import and register call. After the existing `from ace.pages import coding, import_page, landing` line, add `agreement`:

```python
from ace.pages import agreement, coding, import_page, landing
```

And in the registration block, add:

```python
agreement.register()
```

- [ ] **Step 3: Add "Check Agreement" button to landing page**

In `src/ace/pages/landing.py`, find the button row with "New Project" and "Open Project" (around line 126-132). Add a new button in that row:

```python
ui.button(
    "Check Agreement",
    icon="compare_arrows",
    on_click=lambda: ui.navigate.to("/agreement"),
).props("outline no-caps")
```

- [ ] **Step 4: Test manually**

Run: `uv run ace`

1. Navigate to http://127.0.0.1:8080
2. Verify "Check Agreement" button appears on landing page
3. Click it — should navigate to `/agreement`
4. Verify empty state shows with icon and instructions
5. Click "Add File" — native file picker should open
6. If you have two .ace files with the same source text, add both and verify validation shows green
7. Click "Compute Agreement" and verify dashboard renders

- [ ] **Step 5: Commit**

```bash
git add src/ace/pages/agreement.py src/ace/app.py src/ace/pages/landing.py
git commit -m "feat(agreement): add agreement page with dashboard, CSV export, and methods paragraph"
```

---

## Chunk 5: Run Full Test Suite + Final Verification

### Task 8: Run Full Test Suite

- [ ] **Step 1: Run all tests**

Run: `uv run pytest -v`
Expected: All tests PASS, including new agreement tests and existing tests (no regressions)

- [ ] **Step 2: Fix any failing tests**

If any tests fail, fix the issues and re-run.

- [ ] **Step 3: Run the app and verify manually**

Run: `uv run ace`

Verify:
1. Landing page shows "Check Agreement" button
2. `/agreement` page loads with empty state
3. Adding .ace files shows validation
4. Computing metrics shows dashboard with all tabs
5. CSV export downloads
6. Methods paragraph copies to clipboard
7. Existing pages (landing, import, coding) still work

- [ ] **Step 4: Final commit if needed**

Only if fixes were needed from step 2.

---

## Deferred to Follow-Up

These spec features are intentionally deferred from this plan:

- **Per-source row expansion** — clicking a source row to see an inline annotation overlay with each coder's annotations in distinct colours. Requires adapting coding.py's annotation rendering for read-only multi-coder display. The per-source table itself is fully functional.
- **Setup area collapse** — collapsing to a summary line after computation with "Edit" to re-expand.
- **File remove button** — removing individual files from the comparison.
- **Low-agreement row styling** — amber background + warning icon on low-agreement rows in the per-code table.
- **CSV metadata header row** — comment row with files compared, date, coder names.

These are UI polish items that can be added incrementally without changing the services.

---

## Summary

| Task | What it does | Files |
|------|-------------|-------|
| 1 | Add krippendorff, bump irrCAC | `pyproject.toml` |
| 2 | Data structures | `agreement_types.py` + test |
| 3 | AgreementLoader (file validation, matching, dataset building) | `agreement_loader.py` + test |
| 4 | AgreementComputer (all metrics) | `agreement_computer.py` + test |
| 5 | End-to-end integration tests | `test_agreement_e2e.py` |
| 6 | CSS classes | `theme.css`, `agreement.css` |
| 7 | Agreement page + landing button + app registration | `agreement.py`, `landing.py`, `app.py` |
| 8 | Full test suite verification | — |
