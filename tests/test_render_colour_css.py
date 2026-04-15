"""Tests for the colour CSS emitter used by both initial render and OOB swaps."""
import re

from ace.routes.api import _render_colour_style_oob


def test_render_colour_style_emits_three_rule_types():
    codes = [{"id": "abc123", "colour": "#ff8800"}]
    html = _render_colour_style_oob(codes)

    # Strip the <style> wrapper to inspect the rules directly
    body_match = re.search(r"<style[^>]*>(.*)</style>", html, re.DOTALL)
    assert body_match, f"Expected <style> wrapper, got: {html!r}"
    body = body_match.group(1)

    # 1. Sidebar/chip rule — background-color on .ace-code-{cid}
    assert ".ace-code-abc123" in body
    assert "background-color: rgba(255,136,0" in body

    # 2. SVG rect fill for normal highlights
    assert "rect.ace-hl-abc123" in body
    assert "fill: rgba(255,136,0,0.30" in body

    # 3. SVG rect fill for flash animation
    assert "rect.ace-flash-abc123" in body
    assert "fill: rgba(255,136,0,0.70" in body

    # Legacy CSS Custom Highlight rule REMOVED in Task 3
    assert "::highlight" not in body


def test_render_colour_style_emits_rules_for_each_code():
    codes = [
        {"id": "one", "colour": "#112233"},
        {"id": "two", "colour": "#445566"},
    ]
    html = _render_colour_style_oob(codes)
    # Each code should produce three rule types (no ::highlight() after Task 3)
    assert html.count("rect.ace-hl-") == 2
    assert html.count("rect.ace-flash-") == 2
    assert html.count(".ace-code-") == 2
    assert "::highlight" not in html
