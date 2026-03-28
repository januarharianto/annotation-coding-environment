"""Tests for smart text splitting: lines → list items → sentences."""

from ace.services.text_splitter import split_into_units


def test_empty_text():
    assert split_into_units("") == []


def test_single_sentence():
    units = split_into_units("Hello world.")
    assert len(units) == 1
    assert units[0]["text"] == "Hello world."
    assert units[0]["type"] == "prose"
    assert units[0]["start_offset"] == 0
    assert units[0]["end_offset"] == 12


def test_two_sentences():
    units = split_into_units("First sentence. Second sentence.")
    assert len(units) == 2
    assert units[0]["text"] == "First sentence."
    assert units[1]["text"] == "Second sentence."


def test_abbreviation_not_split():
    units = split_into_units("Dr. Smith said hello.")
    assert len(units) == 1
    assert units[0]["text"] == "Dr. Smith said hello."


def test_eg_abbreviation():
    units = split_into_units("Some items, e.g. apples, are fruit.")
    assert len(units) == 1


def test_decimal_not_split():
    units = split_into_units("The price is 3.5 dollars.")
    assert len(units) == 1


def test_ellipsis_not_split():
    units = split_into_units("He paused... then continued.")
    assert len(units) == 1


def test_exclamation_and_question():
    units = split_into_units("Hello! How are you?")
    assert len(units) == 2
    assert units[0]["text"] == "Hello!"
    assert units[1]["text"] == "How are you?"


def test_list_items_dash():
    text = "- Not enough feedback\n- Group work was unbalanced"
    units = split_into_units(text)
    assert len(units) == 2
    assert units[0]["type"] == "list"
    assert units[1]["type"] == "list"
    assert units[0]["text"] == "- Not enough feedback"
    assert units[1]["text"] == "- Group work was unbalanced"


def test_list_items_numbered():
    text = "1. First item\n2. Second item\n3. Third item"
    units = split_into_units(text)
    assert len(units) == 3
    assert all(u["type"] == "list" for u in units)


def test_list_items_bullet():
    text = "* Item one\n* Item two"
    units = split_into_units(text)
    assert len(units) == 2
    assert all(u["type"] == "list" for u in units)


def test_list_items_roman_numeral():
    text = "(i) First item\n(ii) Second item\n(iii) Third item"
    units = split_into_units(text)
    assert len(units) == 3
    assert all(u["type"] == "list" for u in units)


def test_decimal_at_line_start_not_list():
    """3.5 million should NOT be classified as a list item."""
    text = "3.5 million people were surveyed."
    units = split_into_units(text)
    assert len(units) == 1
    assert units[0]["type"] == "prose"


def test_mixed_prose_and_list():
    text = "Introduction paragraph.\n\n- First point\n- Second point\n\nConclusion here."
    units = split_into_units(text)
    assert units[0]["type"] == "prose"
    assert units[0]["text"] == "Introduction paragraph."
    assert units[1]["type"] == "list"
    assert units[2]["type"] == "list"
    assert units[3]["type"] == "prose"
    assert units[3]["text"] == "Conclusion here."


def test_blank_lines_skipped():
    text = "First paragraph.\n\n\nSecond paragraph."
    units = split_into_units(text)
    assert len(units) == 2


def test_offsets_are_correct_multiline():
    text = "Line one.\n\nLine two."
    units = split_into_units(text)
    assert units[0]["start_offset"] == 0
    assert units[0]["end_offset"] == 9
    assert units[1]["start_offset"] == 11
    assert units[1]["end_offset"] == 20


def test_offsets_correct_for_list_after_prose():
    text = "Some text.\n- Item one\n- Item two"
    units = split_into_units(text)
    assert units[0]["text"] == "Some text."
    assert units[0]["start_offset"] == 0
    assert units[0]["end_offset"] == 10
    assert units[1]["text"] == "- Item one"
    assert units[1]["start_offset"] == 11
    assert units[1]["end_offset"] == 21
    assert units[2]["text"] == "- Item two"
    assert units[2]["start_offset"] == 22
    assert units[2]["end_offset"] == 32


def test_sentence_without_terminal_punctuation():
    units = split_into_units("No punctuation here")
    assert len(units) == 1
    assert units[0]["text"] == "No punctuation here"


def test_multiple_sentences_same_line():
    text = "First. Second. Third."
    units = split_into_units(text)
    assert len(units) == 3


def test_text_roundtrip_offsets():
    """Verify that each unit's offsets correctly index into the original text."""
    text = "Hello world. Goodbye.\n\n- Item A\n- Item B\n\nFinal sentence."
    units = split_into_units(text)
    for unit in units:
        extracted = text[unit["start_offset"]:unit["end_offset"]]
        assert extracted == unit["text"], f"Offset mismatch: {extracted!r} != {unit['text']!r}"
