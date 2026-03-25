"""Annotation text rendering — shared by coding.py and coding_actions.py."""

import html


def _annotation_span(data: dict) -> str:
    hex_c = data["colour"].lstrip("#")
    if len(hex_c) == 6:
        r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    else:
        r, g, b = 153, 153, 153
    return (
        f'<span class="ace-annotation" '
        f'data-annotation-id="{html.escape(data["id"])}" '
        f'title="{html.escape(data["code_name"])}" '
        f'aria-label="{html.escape(data["code_name"])}" '
        f'style="background-color: rgba({r},{g},{b},0.3);">'
    )


def render_annotated_text(text: str, annotations: list, codes_by_id: dict) -> str:
    if not text:
        return ""

    events_list: list[tuple[int, int, str, dict | None]] = []
    for ann in annotations:
        start = ann["start_offset"]
        end = ann["end_offset"]
        code = codes_by_id.get(ann["code_id"])
        colour = code["colour"] if code else "#999999"
        code_name = code["name"] if code else "Unknown"
        events_list.append((start, 0, "open", {
            "id": ann["id"],
            "colour": colour,
            "code_name": code_name,
        }))
        events_list.append((end, 1, "close", {"id": ann["id"]}))

    events_list.sort(key=lambda e: (e[0], e[1]))

    parts: list[str] = []
    pos = 0
    open_stack: list[dict] = []

    for offset, kind_order, kind, data in events_list:
        if offset > pos:
            parts.append(html.escape(text[pos:offset]))
            pos = offset

        if kind == "open":
            parts.append(_annotation_span(data))
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
