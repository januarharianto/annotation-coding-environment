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
        # First pass: collect all (coder_name, file_index, coder_id, path) tuples
        raw: list[tuple[str, int, str, str]] = []
        name_counts: dict[str, int] = {}
        for i, fd in enumerate(self._file_data):
            for coder_id, coder_name in fd["coders"].items():
                raw.append((coder_name, i, coder_id, fd["path"]))
                name_counts[coder_name] = name_counts.get(coder_name, 0) + 1

        # Second pass: disambiguate names that appear more than once or are "default"
        coders: list[CoderInfo] = []
        for coder_name, i, coder_id, path in raw:
            if name_counts[coder_name] > 1 or coder_name == "default":
                label = f"{coder_name} ({Path(path).stem})"
            else:
                label = coder_name
            coders.append(CoderInfo(id=f"{i}_{coder_id}", label=label, source_file=path))

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
