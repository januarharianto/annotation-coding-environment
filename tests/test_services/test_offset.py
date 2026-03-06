from ace.services.offset import codepoint_to_utf16, utf16_to_codepoint


def test_ascii_offsets_unchanged():
    text = "hello world"
    for i in range(len(text) + 1):
        assert utf16_to_codepoint(text, i) == i
        assert codepoint_to_utf16(text, i) == i


def test_emoji_offset_conversion():
    text = "Hi \U0001f60a there"  # "Hi 😊 there"
    # UTF-16 layout: H(1) i(1) space(1) 😊(2) space(1) t h e r e
    # UTF-16 offsets: 0    1    2        3,4    5        6 7 8 9 10
    # Codepoint:      0    1    2        3      4        5 6 7 8 9

    # JS offset 5 (space after emoji) -> Python offset 4
    assert utf16_to_codepoint(text, 5) == 4
    # Python offset 4 (space after emoji) -> JS offset 5
    assert codepoint_to_utf16(text, 4) == 5


def test_multiple_emoji():
    text = "a\U0001f60ab\U0001f60ac"  # "a😊b😊c"
    # UTF-16 layout: a(1) 😊(2)   b(1) 😊(2)   c(1)
    # UTF-16 offsets: 0    1,2     3    4,5     6
    # Codepoint:      0    1       2    3       4

    assert utf16_to_codepoint(text, 0) == 0  # 'a'
    assert utf16_to_codepoint(text, 1) == 1  # start of first emoji
    assert utf16_to_codepoint(text, 3) == 2  # 'b'
    assert utf16_to_codepoint(text, 4) == 3  # start of second emoji
    assert utf16_to_codepoint(text, 6) == 4  # 'c'

    assert codepoint_to_utf16(text, 0) == 0  # 'a'
    assert codepoint_to_utf16(text, 1) == 1  # first emoji
    assert codepoint_to_utf16(text, 2) == 3  # 'b'
    assert codepoint_to_utf16(text, 3) == 4  # second emoji
    assert codepoint_to_utf16(text, 4) == 6  # 'c'


def test_no_emoji_roundtrip():
    text = "plain text"
    for i in range(len(text) + 1):
        utf16_off = codepoint_to_utf16(text, i)
        assert utf16_to_codepoint(text, utf16_off) == i
