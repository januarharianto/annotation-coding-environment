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
    """Render source text as sentence spans with stacked underline annotations.

    Supports multiple overlapping codes per sentence. Each annotation adds
    a coloured underline at increasing offset (3px, 6px, 9px...).
    Partial annotations (custom selections) are rendered as inner <mark> spans.
    """
    if not units:
        return ""

    parts: list[str] = []

    for i, unit in enumerate(units):
        if _is_para_break(i, units):
            parts.append('<span class="ace-para-break"></span>')

        overlapping = _get_sentence_annotations(unit, annotations, codes_by_id)

        classes = ["ace-sentence"]
        if unit["type"] == "list":
            classes.append("ace-sentence--list")
        if overlapping:
            classes.append("ace-sentence--coded")

        s = unit["start_offset"]
        e = unit["end_offset"]
        cls = " ".join(classes)
        inner = _render_inner_text(unit["text"], s, overlapping)

        parts.append(
            f'<span id="s-{i}" class="{cls}" data-idx="{i}" data-start="{s}" data-end="{e}">{inner}</span> '
        )

    return "".join(parts)


def _get_sentence_annotations(
    unit: dict, annotations: list[dict], codes_by_id: dict,
) -> list[dict]:
    """Find ALL annotations that overlap this sentence, with colour info."""
    start = unit["start_offset"]
    end = unit["end_offset"]
    result = []

    for ann in annotations:
        if ann["start_offset"] < end and ann["end_offset"] > start:
            code = codes_by_id.get(ann["code_id"])
            if code:
                result.append({
                    "annotation_id": ann["id"],
                    "code_id": ann["code_id"],
                    "colour": code["colour"],
                    "start_offset": ann["start_offset"],
                    "end_offset": ann["end_offset"],
                })
    return result


_UNDERLINE_OFFSETS = [3, 6, 9, 12, 15]


def _render_inner_text(
    text: str, unit_start: int, overlapping: list[dict],
) -> str:
    """Render sentence text with stacked underlines for each annotation.

    Full-sentence annotations: underline the whole text.
    Partial annotations: underline only the selected range via <mark>.
    """
    if not overlapping:
        return html.escape(text)

    # Build underline events: each annotation marks its range within this sentence
    unit_end = unit_start + len(text)
    events: list[tuple[int, int, str, dict]] = []  # (offset, order, type, ann)
    for ann in overlapping:
        rel_start = max(0, ann["start_offset"] - unit_start)
        rel_end = min(len(text), ann["end_offset"] - unit_start)
        events.append((rel_start, 0, "open", ann))
        events.append((rel_end, 1, "close", ann))

    events.sort(key=lambda e: (e[0], e[1]))

    # Check if all annotations cover the full sentence (common case: sentence-level coding)
    all_full = all(
        ann["start_offset"] <= unit_start and ann["end_offset"] >= unit_end
        for ann in overlapping
    )

    if all_full:
        # Simple case: stacked underlines on the whole sentence
        style_parts = []
        colors = []
        for idx, ann in enumerate(overlapping):
            offset_px = _UNDERLINE_OFFSETS[idx] if idx < len(_UNDERLINE_OFFSETS) else 15
            colors.append(ann["colour"])
            style_parts.append(f"{ann['colour']} {offset_px}px")
        # Use box-shadow for stacked underlines (more reliable than text-decoration stacking)
        shadows = ", ".join(f"inset 0 -{px}px 0 {c}" for c, px in zip(colors, [2] + [2] * (len(colors) - 1)) for _ in [None])
        # Actually, simpler: use multiple box-shadows at different y-offsets
        shadow_list = []
        for idx, ann in enumerate(overlapping):
            offset_px = _UNDERLINE_OFFSETS[idx] if idx < len(_UNDERLINE_OFFSETS) else 15
            shadow_list.append(f"inset 0 -{offset_px}px 0 -1px {ann['colour']}")
        style = f' style="text-decoration:none;box-shadow:{",".join(shadow_list)};"'
        escaped = html.escape(text)
        return f"<span{style}>{escaped}</span>"

    # Complex case: partial annotations — render with <mark> tags for each range
    # Sort events and walk through text building segments
    pos = 0
    result: list[str] = []
    active: list[dict] = []

    for offset, order, kind, ann in events:
        if offset > pos:
            segment = html.escape(text[pos:offset])
            if active:
                segment = _wrap_underlines(segment, active)
            result.append(segment)
            pos = offset

        if kind == "open":
            active.append(ann)
        else:
            active = [a for a in active if a["annotation_id"] != ann["annotation_id"]]

    if pos < len(text):
        segment = html.escape(text[pos:])
        if active:
            segment = _wrap_underlines(segment, active)
        result.append(segment)

    return "".join(result)


def _wrap_underlines(text: str, annotations: list[dict]) -> str:
    """Wrap text in a <mark> with stacked underline styles."""
    shadow_list = []
    for idx, ann in enumerate(annotations):
        offset_px = _UNDERLINE_OFFSETS[idx] if idx < len(_UNDERLINE_OFFSETS) else 15
        shadow_list.append(f"inset 0 -{offset_px}px 0 -1px {ann['colour']}")
    style = f"background:transparent;box-shadow:{','.join(shadow_list)};"
    return f'<mark style="{style}">{text}</mark>'


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
    """Build merged annotation groups for the right margin panel.

    Adjacent sentences coded with the same code are visually merged
    into a single margin note. Returns list of dicts with keys:
        code_id, code_name, colour, start_idx, end_idx, texts
    """
    if not units or not annotations:
        return []

    # Map each annotation to the sentence index it overlaps
    ann_sentences: list[tuple[int, dict]] = []
    for ann in annotations:
        for i, unit in enumerate(units):
            if ann["start_offset"] < unit["end_offset"] and ann["end_offset"] > unit["start_offset"]:
                ann_sentences.append((i, ann))
                break

    # Sort by sentence index
    ann_sentences.sort(key=lambda x: x[0])

    # Group adjacent same-code annotations
    groups: list[dict] = []
    for sent_idx, ann in ann_sentences:
        code = codes_by_id.get(ann["code_id"])
        if not code:
            continue

        if (
            groups
            and groups[-1]["code_id"] == ann["code_id"]
            and groups[-1]["end_idx"] == sent_idx - 1
        ):
            groups[-1]["end_idx"] = sent_idx
            groups[-1]["texts"].append(ann.get("selected_text") or units[sent_idx]["text"])
        else:
            groups.append({
                "code_id": ann["code_id"],
                "code_name": code["name"],
                "colour": code["colour"],
                "start_idx": sent_idx,
                "end_idx": sent_idx,
                "texts": [ann.get("selected_text") or units[sent_idx]["text"]],
            })

    return groups
