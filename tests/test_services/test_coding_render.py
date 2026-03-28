"""Tests for sentence-based text rendering."""

from ace.services.coding_render import render_sentence_text


def test_empty_units():
    assert render_sentence_text([], [], {}) == ""


def test_single_uncoded_sentence():
    units = [{"text": "Hello world.", "type": "prose", "start_offset": 0, "end_offset": 12}]
    html = render_sentence_text(units, [], {})
    assert 'class="ace-sentence"' in html
    assert 'data-idx="0"' in html
    assert "Hello world." in html


def test_coded_sentence():
    units = [{"text": "Hello.", "type": "prose", "start_offset": 0, "end_offset": 6}]
    annotations = [{"id": "a1", "code_id": "c1", "start_offset": 0, "end_offset": 6, "selected_text": "Hello."}]
    codes_by_id = {"c1": {"id": "c1", "name": "Greeting", "colour": "#e53935"}}
    html = render_sentence_text(units, annotations, codes_by_id)
    assert "ace-sentence--coded" in html
    assert "--code-color:#e53935" in html


def test_uncoded_sentence_no_style():
    units = [{"text": "Hello.", "type": "prose", "start_offset": 0, "end_offset": 6}]
    html = render_sentence_text(units, [], {})
    assert "ace-sentence--coded" not in html
    assert "--code-color" not in html


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


def test_annotation_data_attribute():
    units = [{"text": "Hello.", "type": "prose", "start_offset": 0, "end_offset": 6}]
    annotations = [{"id": "a1", "code_id": "c1", "start_offset": 0, "end_offset": 6, "selected_text": "Hello."}]
    codes_by_id = {"c1": {"id": "c1", "name": "Test", "colour": "#000000"}}
    html = render_sentence_text(units, annotations, codes_by_id)
    assert 'data-annotation-id="a1"' in html
    assert 'data-code-id="c1"' in html
