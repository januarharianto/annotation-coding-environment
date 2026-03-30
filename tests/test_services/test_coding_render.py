"""Tests for sentence-based text rendering (no highlight markup)."""

from ace.services.coding_render import render_sentence_text


def test_empty_units():
    assert render_sentence_text([], [], {}) == ""


def test_single_uncoded_sentence():
    units = [{"text": "Hello world.", "type": "prose", "start_offset": 0, "end_offset": 12}]
    html = render_sentence_text(units, [], {})
    assert 'class="ace-sentence"' in html
    assert 'data-idx="0"' in html
    assert "Hello world." in html


def test_coded_sentence_has_coded_class():
    units = [{"text": "Hello.", "type": "prose", "start_offset": 0, "end_offset": 6}]
    annotations = [{"id": "a1", "code_id": "c1", "start_offset": 0, "end_offset": 6}]
    codes_by_id = {"c1": {"id": "c1", "name": "Greeting", "colour": "#e53935"}}
    html = render_sentence_text(units, annotations, codes_by_id)
    assert "ace-sentence--coded" in html
    assert "<mark" not in html


def test_uncoded_sentence_no_coded_class():
    units = [{"text": "Hello.", "type": "prose", "start_offset": 0, "end_offset": 6}]
    html = render_sentence_text(units, [], {})
    assert "ace-sentence--coded" not in html


def test_list_item_class():
    units = [{"text": "- Item one", "type": "list", "start_offset": 0, "end_offset": 10}]
    html = render_sentence_text(units, [], {})
    assert "ace-sentence--list" in html


def test_paragraph_break_between_types():
    units = [
        {"text": "Prose.", "type": "prose", "start_offset": 0, "end_offset": 6},
        {"text": "- List", "type": "list", "start_offset": 8, "end_offset": 14},
    ]
    html = render_sentence_text(units, [], {})
    assert "ace-para-break" in html


def test_paragraph_break_blank_line():
    units = [
        {"text": "First.", "type": "prose", "start_offset": 0, "end_offset": 6},
        {"text": "Second.", "type": "prose", "start_offset": 8, "end_offset": 15},
    ]
    html = render_sentence_text(units, [], {})
    assert "ace-para-break" in html


def test_no_paragraph_break_same_line():
    units = [
        {"text": "First.", "type": "prose", "start_offset": 0, "end_offset": 6},
        {"text": "Second.", "type": "prose", "start_offset": 7, "end_offset": 14},
    ]
    html = render_sentence_text(units, [], {})
    assert "ace-para-break" not in html


def test_sentence_id_attribute():
    units = [{"text": "Hello.", "type": "prose", "start_offset": 0, "end_offset": 6}]
    html = render_sentence_text(units, [], {})
    assert 'id="s-0"' in html


def test_html_escaping():
    units = [{"text": "A < B & C > D", "type": "prose", "start_offset": 0, "end_offset": 13}]
    html = render_sentence_text(units, [], {})
    assert "A &lt; B &amp; C &gt; D" in html


def test_data_start_end_attributes():
    units = [{"text": "Hello.", "type": "prose", "start_offset": 5, "end_offset": 11}]
    html = render_sentence_text(units, [], {})
    assert 'data-start="5"' in html
    assert 'data-end="11"' in html


def test_no_mark_elements_with_annotations():
    """Annotations produce ace-sentence--coded class but no <mark> elements."""
    units = [{"text": "Hello.", "type": "prose", "start_offset": 0, "end_offset": 6}]
    annotations = [
        {"id": "a1", "code_id": "c1", "start_offset": 0, "end_offset": 6},
        {"id": "a2", "code_id": "c2", "start_offset": 0, "end_offset": 6},
    ]
    codes_by_id = {
        "c1": {"id": "c1", "name": "Red", "colour": "#e53935"},
        "c2": {"id": "c2", "name": "Blue", "colour": "#1e88e5"},
    }
    html = render_sentence_text(units, annotations, codes_by_id)
    assert "ace-sentence--coded" in html
    assert "<mark" not in html
    assert "rgba(" not in html


def test_partial_annotation_no_mark():
    """Custom selection within a sentence: no <mark>, just ace-sentence--coded."""
    units = [{"text": "Hello world.", "type": "prose", "start_offset": 0, "end_offset": 12}]
    annotations = [{"id": "a1", "code_id": "c1", "start_offset": 6, "end_offset": 11}]
    codes_by_id = {"c1": {"id": "c1", "name": "Test", "colour": "#43a047"}}
    html = render_sentence_text(units, annotations, codes_by_id)
    assert "ace-sentence--coded" in html
    assert "<mark" not in html


