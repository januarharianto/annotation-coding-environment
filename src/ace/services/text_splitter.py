"""Smart text splitting: lines → list items → sentences.

Uses pySBD for robust sentence boundary detection (handles abbreviations,
decimals, ellipsis, URLs, quoted speech). Custom list-item detection on top.
"""

import re

import pysbd

# List markers: -, *, •, numbered, lettered, roman numerals in parens
# Negative lookahead (?!\d) prevents "3.5 million" matching as a numbered list
_LIST_RE = re.compile(
    r"^(\s*)"
    r"("
    r"[-*\u2022]"                     # dash, asterisk, bullet
    r"|\d+[.)](?!\d)"                 # 1. or 1) but NOT 3.5
    r"|[a-z][.)]"                     # a. or a)
    r"|\(\d+\)"                       # (1)
    r"|\([a-z]+\)"                    # (a), (i), (ii), (iii), (iv)
    r"|[ivxlcdm]{1,6}[.)]"            # i. ii. iii. iv. (roman numerals, max 6 chars to avoid false positives like "dim." "mix.")
    r")\s+",
    re.IGNORECASE,
)

# pySBD segmenter (English, reusable)
_segmenter = pysbd.Segmenter(language="en", clean=False, char_span=True)


def split_into_units(text: str) -> list[dict]:
    """Split text into codeable units: sentences and list items.

    Returns list of dicts with keys:
        text: str — the unit text (stripped)
        type: "prose" | "list"
        start_offset: int — character offset in original text
        end_offset: int — character offset (exclusive) in original text
    """
    if not text:
        return []

    lines = text.split("\n")
    units: list[dict] = []
    offset = 0  # cumulative char position in original text

    for i, raw_line in enumerate(lines):
        stripped = raw_line.strip()

        if not stripped:
            offset += len(raw_line) + (1 if i < len(lines) - 1 else 0)
            continue

        # Start of content in original text (skip leading whitespace)
        content_start = offset + len(raw_line) - len(raw_line.lstrip())

        if _LIST_RE.match(stripped):
            units.append({
                "text": stripped,
                "type": "list",
                "start_offset": content_start,
                "end_offset": content_start + len(stripped),
            })
        else:
            # Use pySBD for sentence splitting with character spans
            spans = _segmenter.segment(stripped)
            for span in spans:
                sent_text = span.sent.strip()
                if not sent_text:
                    continue
                # pySBD start offset is within the stripped line; end may include
                # trailing whitespace so we derive end from start + stripped length.
                # Account for leading whitespace pySBD may include in span.sent.
                leading = len(span.sent) - len(span.sent.lstrip())
                abs_start = content_start + span.start + leading
                abs_end = abs_start + len(sent_text)
                units.append({
                    "text": sent_text,
                    "type": "prose",
                    "start_offset": abs_start,
                    "end_offset": abs_end,
                })

        offset += len(raw_line) + (1 if i < len(lines) - 1 else 0)

    return units
