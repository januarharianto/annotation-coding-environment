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


