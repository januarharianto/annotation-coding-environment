"""Annotation text rendering — shared by coding.py and coding_actions.py."""

import html


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
            existing_ids = {c["code_id"] for c in merged[-1]["codes"]}
            for c in group["codes"]:
                if c["code_id"] not in existing_ids:
                    merged[-1]["codes"].append(c)
                    existing_ids.add(c["code_id"])
        else:
            merged.append(group)

    return merged
