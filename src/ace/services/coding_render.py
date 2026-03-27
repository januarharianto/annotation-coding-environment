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
