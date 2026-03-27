"""Tests for CSS-class-based annotation rendering."""

from ace.pages.coding_render import render_annotated_text


def test_render_plain_text():
    html = render_annotated_text("Hello world", [], {})
    assert "Hello world" in html
    assert "<span" not in html


def test_render_single_annotation():
    annotations = [{"id": "a1", "code_id": "c1", "start_offset": 0, "end_offset": 5, "selected_text": "Hello"}]
    codes = {"c1": {"id": "c1", "name": "Code1", "colour": "#FF0000"}}
    html = render_annotated_text("Hello world", annotations, codes)
    assert 'class="ace-annotation ace-code-c1"' in html
    assert 'id="ann-a1"' in html
    assert 'data-annotation-id="a1"' in html
    assert 'title="Code1"' in html


def test_render_escapes_text():
    html = render_annotated_text("<script>alert('xss')</script>", [], {})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_empty_text():
    html = render_annotated_text("", [], {})
    assert html == ""


def test_render_adjacent_annotations():
    annotations = [
        {"id": "a1", "code_id": "c1", "start_offset": 0, "end_offset": 5, "selected_text": "Hello"},
        {"id": "a2", "code_id": "c2", "start_offset": 6, "end_offset": 11, "selected_text": "world"},
    ]
    codes = {
        "c1": {"id": "c1", "name": "Code1", "colour": "#FF0000"},
        "c2": {"id": "c2", "name": "Code2", "colour": "#00FF00"},
    }
    html = render_annotated_text("Hello world", annotations, codes)
    assert "ace-code-c1" in html
    assert "ace-code-c2" in html
    assert "ann-a1" in html
    assert "ann-a2" in html
