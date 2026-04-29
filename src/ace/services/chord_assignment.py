"""Mnemonic 2-letter chord assignment for codebook codes.

Used when a project has more than 31 codes — the keyboard's single-key slots
(1-9, 0, a-p minus n, r-y minus v and x) total 31, so the 32nd code onward
gets a chord shortcut (;<chord>) instead.

The algorithm prefers mnemonic chords (first letters of distinctive words in
the name) so users can guess shortcuts without memorising. Collisions are
resolved by walking through consonants, then alphabet.
"""

import string

# Words skipped when picking initial letters. Short, generic, content-free.
STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "and", "or", "of", "the", "to", "in", "on",
    "at", "with", "for", "by",
})

_CONSONANTS = "bcdfghjklmnpqrstvwxyz"
_LOWERCASE = string.ascii_lowercase


def _meaningful_words(name: str) -> list[str]:
    """Lowercase the name; split on whitespace; drop stop-words; drop empties."""
    words = [w.lower() for w in name.split() if w.strip()]
    return [w for w in words if w not in STOP_WORDS]


def _ascii_letters(word: str) -> str:
    """Strip non-ASCII-letter characters from a word."""
    return "".join(c for c in word if c in _LOWERCASE)


def _try_chord(chord: str, taken: set[str]) -> str | None:
    """Return chord if it's 2 ASCII lowercase letters and not taken, else None."""
    if len(chord) == 2 and chord[0] in _LOWERCASE and chord[1] in _LOWERCASE:
        if chord not in taken:
            return chord
    return None


def _alphabetical_pair(taken: set[str]) -> str:
    """Return the first 2-letter pair (aa, ab, ac...) not in taken."""
    for first in _LOWERCASE:
        for second in _LOWERCASE:
            chord = first + second
            if chord not in taken:
                return chord
    raise RuntimeError("Chord space exhausted: all 676 alphabetical pairs taken")


def assign_chord(name: str, taken: set[str]) -> str:
    """Pick a 2-letter chord for `name` that isn't in `taken`.

    Algorithm:
    1. Tokenise; drop stop-words.
    2. If 2+ words: try first letter of word 1 + first letter of word 2.
    3. If 1 word: try first 2 letters.
    4. On collision: walk consonants of word 2, then word 1, then alphabet.
    5. If first letter is non-ASCII or words list is empty: alphabetical fallback.
    6. All 26 alphabetical fallbacks for the same first letter exhausted: RuntimeError.
    """
    words = _meaningful_words(name)

    # Empty / pure non-ASCII → alphabetical from start
    if not words:
        return _alphabetical_pair(taken)

    word1 = _ascii_letters(words[0])
    if not word1:
        return _alphabetical_pair(taken)

    first = word1[0]
    word2 = _ascii_letters(words[1]) if len(words) >= 2 else ""

    # Pick initial second letter
    if word2:
        second = word2[0]
    else:
        second = word1[1] if len(word1) > 1 else first

    # Initial guess
    if (chord := _try_chord(first + second, taken)):
        return chord

    # Cascade: walk consonants of word 2 (if any)
    for letter in word2[1:]:  # skip already-tried first letter
        if letter in _CONSONANTS:
            if (chord := _try_chord(first + letter, taken)):
                return chord

    # Cascade: walk consonants of word 1
    for letter in word1[1:]:
        if letter in _CONSONANTS:
            if (chord := _try_chord(first + letter, taken)):
                return chord

    # Cascade: walk full alphabet for second letter
    for letter in _LOWERCASE:
        if (chord := _try_chord(first + letter, taken)):
            return chord

    # All `first*` chords taken
    raise RuntimeError(f"Chord space exhausted: all 26 chords for prefix '{first}' are taken")
