"""Convert between UTF-16 code unit offsets and Unicode code point offsets."""


def utf16_to_codepoint(text: str, utf16_offset: int) -> int:
    """Convert a UTF-16 code unit offset to a Unicode code point offset."""
    utf16_pos = 0
    for cp_pos, char in enumerate(text):
        if utf16_pos >= utf16_offset:
            return cp_pos
        utf16_pos += 2 if ord(char) > 0xFFFF else 1
    return len(text)


def codepoint_to_utf16(text: str, cp_offset: int) -> int:
    """Convert a Unicode code point offset to a UTF-16 code unit offset."""
    utf16_pos = 0
    for cp_pos, char in enumerate(text):
        if cp_pos >= cp_offset:
            return utf16_pos
        utf16_pos += 2 if ord(char) > 0xFFFF else 1
    return utf16_pos
