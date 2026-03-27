"""Tests for palette functions absorbed into codebook module."""

from ace.models.codebook import COLOUR_PALETTE, next_colour


def test_palette_has_36_entries():
    assert len(COLOUR_PALETTE) == 36


def test_palette_entries_are_hex_tuples():
    for hex_val, label in COLOUR_PALETTE:
        assert hex_val.startswith("#")
        assert len(hex_val) == 7
        assert label.startswith("Colour ")


def test_next_colour_returns_hex_string():
    c = next_colour(0)
    assert isinstance(c, str)
    assert c.startswith("#")
    assert len(c) == 7


def test_next_colour_cycles_at_36():
    assert next_colour(0) == next_colour(36)
    assert next_colour(1) == next_colour(37)
    assert next_colour(35) == next_colour(71)
