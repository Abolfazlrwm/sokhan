"""Rule-based Persian punctuation restoration (the v1.4 roadmap post-pass).

faster-whisper emits raw word streams with almost no punctuation. This pass
puts the transcript back into publishable shape with three conservative,
deterministic rule families — no model call, no LLM dependency:

1. Script fix: the Latin comma, question mark and semicolon become their
   Persian counterparts (، ؟ ؛). A comma that groups digits ("1,000",
   "12,500,000") is a thousands separator, not punctuation, and is kept.
2. Spacing: no space *before* punctuation, exactly one space *after* clause
   and sentence punctuation. `.` and `:` are deliberately left alone so
   decimals ("3.5") and clock times ("12:30") survive.
3. Terminal marks: a segment that reads as a question (contains one of the
   question words: آیا، چرا، چطور، کجا، کدام، …) ends with `؟`; anything
   else ends with `.` — appended only when the segment does not already end
   with punctuation.

The worker pipeline applies this per merged segment when
`PUNCTUATION_ENABLED` (default on). The WER benchmark path is untouched,
so the measured numbers stay comparable across releases.
"""

from __future__ import annotations

import re

# Latin forms that should not survive in a Persian transcript.
_LATIN_TO_PERSIAN = str.maketrans({",": "،", "?": "؟", ";": "؛"})

# A comma between a digit and exactly three more digits groups a number.
# \d matches Persian digits too, so "۱,۲۰۰" is covered.
_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
# Stands in for a thousands comma while the Latin marks are translated.
_KEPT_COMMA = "\x00"

_CLAUSE = "،؛"
_SENTENCE_END = "؟!…."
_PUNCT_CHARS = _CLAUSE + _SENTENCE_END + ":."

_SPACE_BEFORE = re.compile(r"\s+([،؛:.!?؟…])")
# One space after clause/sentence punctuation unless another punctuation
# mark or the end of the text follows (`.` and `:` excluded on purpose).
_SPACE_AFTER = re.compile(r"([،؛؟!…])(?=[^\s،؛:.!?؟…])")
_WS_RUNS = re.compile(r"\s{2,}")

_QUESTION_WORDS = frozenset(
    {
        "آیا",
        "چرا",
        "چطور",
        "چطوره",
        "چگونه",
        "چقدر",
        "کی",
        "کیه",
        "کِی",
        "کجا",
        "کجاست",
        "کجای",
        "کدام",
        "کدوم",
        "چیه",
    }
)

# Punctuation and quote marks stripped from token edges before the question
# check, so "چطوره،" and «کی؟» still count as question words.
_TOKEN_EDGES = "،؛:.!?؟…«»()\"'\u200c"


def _is_question(text: str) -> bool:
    return any(
        token.strip(_TOKEN_EDGES) in _QUESTION_WORDS for token in text.split()
    )


def _has_terminal(text: str) -> bool:
    return bool(text) and text[-1] in _PUNCT_CHARS


def restore_punctuation(text: str) -> str:
    """Return `text` with Persian punctuation restored; safe to re-apply."""
    cleaned = _THOUSANDS_COMMA.sub(_KEPT_COMMA, text)
    cleaned = cleaned.translate(_LATIN_TO_PERSIAN).replace(_KEPT_COMMA, ",").strip()
    cleaned = _SPACE_BEFORE.sub(r"\1", cleaned)
    cleaned = _SPACE_AFTER.sub(r"\1 ", cleaned)
    cleaned = _WS_RUNS.sub(" ", cleaned).strip()
    if not cleaned or _has_terminal(cleaned):
        return cleaned
    return cleaned + ("؟" if _is_question(cleaned) else ".")
