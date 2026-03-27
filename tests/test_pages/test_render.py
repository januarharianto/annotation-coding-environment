"""Tests for the annotation text renderer."""

from ace.pages.coding import render_annotated_text


def _ann(id, code_id, start, end, selected_text="text"):
    """Create a fake annotation dict."""
    return {
        "id": id,
        "code_id": code_id,
        "start_offset": start,
        "end_offset": end,
        "selected_text": selected_text,
    }


def _codes():
    return {
        "c1": {"colour": "#FF0000", "name": "Red"},
        "c2": {"colour": "#00FF00", "name": "Green"},
    }


def test_no_annotations():
    result = render_annotated_text("Hello world", [], _codes())
    assert result == "Hello world"


def test_empty_text():
    result = render_annotated_text("", [], _codes())
    assert result == ""


def test_single_annotation():
    anns = [_ann("a1", "c1", 0, 5)]
    result = render_annotated_text("Hello world", anns, _codes())
    assert "<span" in result
    assert 'class="ace-annotation ace-code-c1"' in result
    assert 'id="ann-a1"' in result
    assert 'data-annotation-id="a1"' in result
    assert 'title="Red"' in result
    assert "Hello" in result
    assert " world" in result


def test_two_non_overlapping_annotations():
    anns = [
        _ann("a1", "c1", 0, 5),
        _ann("a2", "c2", 6, 11),
    ]
    result = render_annotated_text("Hello world", anns, _codes())
    assert result.count("<span") == 2
    assert result.count("</span>") == 2


def test_overlapping_annotations():
    # "Hello world" with overlapping spans
    anns = [
        _ann("a1", "c1", 0, 8),   # "Hello wo"
        _ann("a2", "c2", 3, 11),  # "lo world"
    ]
    result = render_annotated_text("Hello world", anns, _codes())
    # Both annotations should be present
    assert "a1" in result
    assert "a2" in result
    # The overlap region should have nested spans
    assert result.count("<span") >= 2


def test_html_escaping():
    anns = [_ann("a1", "c1", 0, 5)]
    result = render_annotated_text("<b>Hi</b> world", anns, _codes())
    assert "&lt;b&gt;" in result
    assert "<b>" not in result


def test_aria_label_on_annotation():
    anns = [_ann("a1", "c1", 0, 5)]
    result = render_annotated_text("Hello world", anns, _codes())
    assert 'aria-label="Red"' in result


def test_annotation_at_end_of_text():
    anns = [_ann("a1", "c1", 6, 11)]
    result = render_annotated_text("Hello world", anns, _codes())
    assert "Hello " in result
    assert "world" in result
    assert "<span" in result
