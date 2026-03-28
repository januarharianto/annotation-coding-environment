"""Annotation text rendering — shared by coding.py and coding_actions.py."""

import html


def _annotation_span(data: dict, *, first: bool = False) -> str:
    ann_id = html.escape(data["id"])
    code_id = html.escape(data["code_id"])
    code_name = html.escape(data["code_name"])
    id_attr = f'id="ann-{ann_id}" ' if first else ""
    return (
        f'<span {id_attr}'
        f'class="ace-annotation ace-code-{code_id}" '
        f'data-annotation-id="{ann_id}" '
        f'title="{code_name}" '
        f'aria-label="{code_name}">'
    )


def render_annotated_text(text: str, annotations: list, codes_by_id: dict) -> str:
    if not text:
        return ""

    events_list: list[tuple[int, int, str, dict | None]] = []
    for ann in annotations:
        start = ann["start_offset"]
        end = ann["end_offset"]
        code = codes_by_id.get(ann["code_id"])
        code_name = code["name"] if code else "Unknown"
        events_list.append((start, 0, "open", {
            "id": ann["id"],
            "code_id": ann["code_id"],
            "code_name": code_name,
        }))
        events_list.append((end, 1, "close", {"id": ann["id"]}))

    events_list.sort(key=lambda e: (e[0], e[1]))

    parts: list[str] = []
    pos = 0
    open_stack: list[dict] = []
    seen_ids: set[str] = set()

    for offset, kind_order, kind, data in events_list:
        if offset > pos:
            parts.append(html.escape(text[pos:offset]))
            pos = offset

        if kind == "open":
            first = data["id"] not in seen_ids
            seen_ids.add(data["id"])
            parts.append(_annotation_span(data, first=first))
            open_stack.append(data)
        else:
            target_id = data["id"]
            idx = None
            for i in range(len(open_stack) - 1, -1, -1):
                if open_stack[i]["id"] == target_id:
                    idx = i
                    break
            if idx is not None:
                to_reopen = []
                for i in range(len(open_stack) - 1, idx, -1):
                    parts.append("</span>")
                    to_reopen.append(open_stack[i])
                parts.append("</span>")
                open_stack.pop(idx)
                for item in reversed(to_reopen):
                    parts.append(_annotation_span(item))

    if pos < len(text):
        parts.append(html.escape(text[pos:]))

    for _ in open_stack:
        parts.append("</span>")

    return "".join(parts)


def render_sentence_text(
    units: list[dict],
    annotations: list[dict],
    codes_by_id: dict,
) -> str:
    """Render source text as individual sentence spans with coding state.

    Each unit becomes a <span class="ace-sentence"> with data-idx.
    Coded sentences get --code-color/--code-bg CSS variables and
    data-annotation-id/data-code-id attributes.
    """
    if not units:
        return ""

    parts: list[str] = []
    prev_type = None

    for i, unit in enumerate(units):
        if prev_type is not None and _is_para_break(i, units):
            parts.append('<span class="ace-para-break"></span>')

        ann_info = _get_sentence_annotation(unit, annotations, codes_by_id)

        classes = ["ace-sentence"]
        if unit["type"] == "list":
            classes.append("ace-sentence--list")

        style = ""
        extra_attrs = ""
        if ann_info:
            classes.append("ace-sentence--coded")
            colour = ann_info["colour"]
            r = int(colour[1:3], 16)
            g = int(colour[3:5], 16)
            b = int(colour[5:7], 16)
            style = f' style="--code-color:{colour};--code-bg:rgba({r},{g},{b},0.18);"'
            ann_id = html.escape(ann_info["annotation_id"])
            code_id = html.escape(ann_info["code_id"])
            extra_attrs = f' data-annotation-id="{ann_id}" data-code-id="{code_id}"'

        text = html.escape(unit["text"])
        cls = " ".join(classes)
        parts.append(
            f'<span id="s-{i}" class="{cls}" data-idx="{i}"{style}{extra_attrs}>{text}</span> '
        )
        prev_type = unit["type"]

    return "".join(parts)


def _get_sentence_annotation(
    unit: dict, annotations: list[dict], codes_by_id: dict,
) -> dict | None:
    """Find the first annotation that overlaps this sentence's offset range."""
    start = unit["start_offset"]
    end = unit["end_offset"]

    for ann in annotations:
        ann_start = ann["start_offset"]
        ann_end = ann["end_offset"]
        if ann_start < end and ann_end > start:
            code = codes_by_id.get(ann["code_id"])
            if code:
                return {
                    "annotation_id": ann["id"],
                    "code_id": ann["code_id"],
                    "colour": code["colour"],
                    "code_name": code["name"],
                }
    return None


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
