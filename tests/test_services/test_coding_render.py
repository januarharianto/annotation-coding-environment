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


from ace.services.coding_render import build_margin_annotations


# --- build_margin_annotations tests ---

def _units(*ranges):
    """Helper: create unit dicts from (start, end) tuples."""
    return [
        {"text": f"S{i}", "type": "prose", "start_offset": s, "end_offset": e}
        for i, (s, e) in enumerate(ranges)
    ]


def _ann(ann_id, code_id, start, end):
    """Helper: create annotation dict."""
    return {"id": ann_id, "code_id": code_id, "start_offset": start, "end_offset": end}


_CODES = {
    "c1": {"id": "c1", "name": "Red", "colour": "#e53935"},
    "c2": {"id": "c2", "name": "Blue", "colour": "#1e88e5"},
    "c3": {"id": "c3", "name": "Green", "colour": "#43a047"},
}


def test_margin_empty():
    assert build_margin_annotations([], [], {}) == []
    assert build_margin_annotations(_units((0, 5)), [], _CODES) == []


def test_margin_single_annotation():
    units = _units((0, 10), (11, 20))
    anns = [_ann("a1", "c1", 0, 10)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 1
    assert result[0]["start_idx"] == 0
    assert result[0]["end_idx"] == 0
    assert len(result[0]["codes"]) == 1
    assert result[0]["codes"][0]["code_id"] == "c1"
    assert result[0]["codes"][0]["code_name"] == "Red"
    assert result[0]["codes"][0]["colour"] == "#e53935"


def test_margin_adjacent_same_code_merges():
    units = _units((0, 10), (11, 20), (21, 30))
    anns = [_ann("a1", "c1", 0, 10), _ann("a2", "c1", 11, 20)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 1
    assert result[0]["start_idx"] == 0
    assert result[0]["end_idx"] == 1


def test_margin_adjacent_different_codes_separate():
    units = _units((0, 10), (11, 20))
    anns = [_ann("a1", "c1", 0, 10), _ann("a2", "c2", 11, 20)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 2


def test_margin_same_range_overlap_grouped():
    """Two different codes on the same sentence merge into one group."""
    units = _units((0, 10), (11, 20))
    anns = [_ann("a1", "c1", 0, 10), _ann("a2", "c2", 0, 10)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 1
    assert result[0]["start_idx"] == 0
    assert result[0]["end_idx"] == 0
    assert len(result[0]["codes"]) == 2
    code_ids = {c["code_id"] for c in result[0]["codes"]}
    assert code_ids == {"c1", "c2"}


def test_margin_partial_overlap_separate():
    """Different ranges get separate groups even if they overlap."""
    units = _units((0, 10), (11, 20), (21, 30))
    anns = [_ann("a1", "c1", 0, 20), _ann("a2", "c2", 11, 30)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 2
    assert result[0]["start_idx"] == 0
    assert result[1]["start_idx"] == 1


def test_margin_cross_sentence_annotation():
    """A single annotation spanning 3 sentences maps to all of them."""
    units = _units((0, 10), (11, 20), (21, 30))
    anns = [_ann("a1", "c1", 0, 30)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 1
    assert result[0]["start_idx"] == 0
    assert result[0]["end_idx"] == 2


def test_margin_gap_no_merge():
    """Same code on non-adjacent sentences stays separate."""
    units = _units((0, 10), (11, 20), (21, 30))
    anns = [_ann("a1", "c1", 0, 10), _ann("a2", "c1", 21, 30)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 2


def test_margin_unknown_code_skipped():
    units = _units((0, 10))
    anns = [_ann("a1", "unknown", 0, 10)]
    result = build_margin_annotations(units, anns, _CODES)
    assert len(result) == 0


def test_margin_no_texts_field():
    """New return type has no 'texts' field."""
    units = _units((0, 10))
    anns = [_ann("a1", "c1", 0, 10)]
    result = build_margin_annotations(units, anns, _CODES)
    assert "texts" not in result[0]
