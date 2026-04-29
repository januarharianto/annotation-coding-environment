"""Unit tests for chord_assignment.assign_chord()."""

import pytest

from ace.services.chord_assignment import assign_chord, STOP_WORDS


class TestBasic:
    def test_two_word_name_first_letters(self):
        assert assign_chord("Privacy data", set()) == "pd"

    def test_three_word_first_two_letters(self):
        assert assign_chord("Privacy of data", set()) == "pd"

    def test_single_word_first_two_letters(self):
        assert assign_chord("Repetitive", set()) == "re"

    def test_drops_stop_words(self):
        assert assign_chord("To give feedback on draft", set()) == "gf"

    def test_lowercases(self):
        assert assign_chord("AI Replacing Humans", set()) == "ar"


class TestCollisions:
    def test_collision_walks_consonants_of_word_two(self):
        assert assign_chord("Privacy data", {"pd"}) == "pt"  # next consonant in 'data'

    def test_collision_walks_consonants_of_word_one(self):
        assert assign_chord("Privacy data", {"pd", "pt"}) == "pr"  # consonant in 'privacy'

    def test_collision_alphabetical_fallback(self):
        # Both consonants exhausted, fall back to walking alphabet
        taken = {"pd", "pt", "pr", "pv", "pc", "py"}
        result = assign_chord("Privacy data", taken)
        assert result == "pa"


class TestNumericEscape:
    def test_falls_back_to_numeric_after_alphabet_exhausted(self):
        taken = {"p" + c for c in "abcdefghijklmnopqrstuvwxyz"}
        result = assign_chord("Privacy", taken)
        assert result == "p1"

    def test_continues_numeric(self):
        taken = {"p" + c for c in "abcdefghijklmnopqrstuvwxyz"} | {"p1"}
        result = assign_chord("Privacy", taken)
        assert result == "p2"


class TestNonAscii:
    def test_emoji_name_alphabetical_fallback(self):
        assert assign_chord("🌱", set()) == "aa"

    def test_emoji_collides(self):
        assert assign_chord("🌱", {"aa"}) == "ab"

    def test_chinese_alphabetical_fallback(self):
        assert assign_chord("测试", set()) == "aa"

    def test_empty_name_alphabetical(self):
        assert assign_chord("", set()) == "aa"


class TestStopList:
    def test_stop_list_documented(self):
        assert "of" in STOP_WORDS
        assert "the" in STOP_WORDS
        assert "and" in STOP_WORDS

    def test_keeps_meaningful_short_words(self):
        # 'use' is meaningful, not a stop-word — it survives as word1 after stop-words drop
        assert assign_chord("To the use of tools", set()) == "ut"  # 'use' + 'tools'
        # 'AI' is content-bearing acronym, not a stop-word
        assert assign_chord("AI replacing", set()) == "ar"


class TestPurity:
    def test_same_input_same_output(self):
        result1 = assign_chord("Privacy of data", set())
        result2 = assign_chord("Privacy of data", set())
        assert result1 == result2

    def test_taken_set_not_mutated(self):
        taken = {"pd"}
        before = taken.copy()
        assign_chord("Privacy", taken)
        assert taken == before
