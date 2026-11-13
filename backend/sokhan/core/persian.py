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


def normalize_persian(text: str) -> str:
    """Lowercase and map Arabic look-alikes to Persian equivalents.

    Zero-width non-joiners and tatweel are removed so identical words written
    with different keyboard habits match in archive search.
    """
    lowered = text.lower()
    replaced = "".join(_ARABIC_TO_PERSIAN.get(char, char) for char in lowered)
    return replaced.replace(_ZWNJ, "").replace(_TATWEEL, "")
