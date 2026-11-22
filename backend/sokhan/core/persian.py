"""Helpers for normalizing Persian text (Arabic code points to Persian)."""

# Characters that look identical but come from the Arabic block. Users type
# both depending on keyboard layout, so search must treat them as equal.
_ARABIC_TO_PERSIAN = {
    "\u064a": "\u06cc",  # yeh -> farsi yeh
    "\u0649": "\u06cc",  # alef maksura -> farsi yeh
    "\u0643": "\u06a9",  # kaf -> keheh
    "\u0629": "\u0647",  # teh marbuta -> heh
    "\u0622": "\u0627",  # alef with madda -> alef
    "\u0623": "\u0627",  # alef with hamza above -> alef
    "\u0625": "\u0627",  # alef with hamza below -> alef
}
_ZWNJ = "\u200c"
_TATWEEL = "\u0640"

# Persian and Latin punctuation plus quote marks. Replaced by a space during
# search normalization so a phrase query matches across the sentence marks
# the punctuation-restoration pass adds.
_PUNCTUATION_CHARS = frozenset("،؛:.!?؟…«»()\"'-–—,")


def normalize_persian(text: str) -> str:
    """Lowercase and map Arabic look-alikes to Persian equivalents.

    Zero-width non-joiners and tatweel are removed so identical words written
    with different keyboard habits match in archive search.

    Kept byte-compatible with the WER benchmark and the training pipeline,
    which normalize with this exact function — their measured numbers must
    stay stable, so punctuation handling deliberately lives in
    `normalize_for_search` instead.
    """
    lowered = text.lower()
    replaced = "".join(_ARABIC_TO_PERSIAN.get(char, char) for char in lowered)
    return replaced.replace(_ZWNJ, "").replace(_TATWEEL, "")


def strip_punctuation(text: str) -> str:
    """Replace punctuation marks with spaces (word boundaries stay words)."""
    return "".join(" " if char in _PUNCTUATION_CHARS else char for char in text)


def normalize_for_search(text: str) -> str:
    """Search-key normalization: `normalize_persian` plus punctuation removal.

    The `text_normalized` column and search queries both go through this, so
    "حالت چطوره" keeps matching the "حالت، چطوره؟" the punctuation pass
    now stores. Punctuation marks become spaces and whitespace runs collapse.
    """
    stripped = strip_punctuation(normalize_persian(text))
    return " ".join(stripped.split())
