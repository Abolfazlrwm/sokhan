"""Orthographic polish for Persian ASR output (v2 quality pass).

Whisper writes Persian reasonably but its orthography is sloppy: prefixes
that belong behind a ZWNJ arrive as separate tokens ("می کنی"), the imperative
prefix "ب" is mis-split into the real word "بی" ("بی پوش" for "بپوش"),
Arabic look-alike code points leak through, and Latin digits appear in
Persian sentences.

`polish_transcript` repairs exactly these surface forms — it never rewords
(colloquial speech stays colloquial), so it is safe to apply to BOTH the
reference and the hypothesis in WER evaluation (benchmarks v2) and to the
product transcript in the pipeline. Every rule is deterministic and
unit-tested (`tests/test_fa_polish.py`).

Not a fix for acoustic errors: when the model mishears a word no amount of
text surgery recovers it — that is what bigger checkpoints are for (the
measured stack: small 78.0% -> medium 59.8% WER, see benchmarks/).
"""

from __future__ import annotations

_ZWNJ = "\u200c"

# ---------------------------------------------------------------- characters

# Arabic-block look-alikes -> Persian. Deliberately does NOT touch alef
# variants (آ أ إ) — polish is for display, unlike the search normalizer.
_ARABIC_CHARS = {
    "\u064a": "\u06cc",  # yeh -> farsi yeh
    "\u0649": "\u06cc",  # alef maksura -> farsi yeh
    "\u0643": "\u06a9",  # kaf -> keheh
    "\u0629": "\u0647",  # teh marbuta -> heh
    "\u0640": "",        # tatweel -> drop
    # Arabic-Indic digits -> Persian digits
    "\u0660": "\u06f0", "\u0661": "\u06f1", "\u0662": "\u06f2", "\u0663": "\u06f3",
    "\u0664": "\u06f4", "\u0665": "\u06f5", "\u0666": "\u06f6", "\u0667": "\u06f7",
    "\u0668": "\u06f8", "\u0669": "\u06f9",
}

# Latin digits -> Persian digits (Persian-first product).
_LATIN_DIGITS = {d: chr(0x06F0 + i) for i, d in enumerate("0123456789")}

# ------------------------------------------------------------------- lexicon

# Very common verbs Whisper writes without the ZWNJ: "میکنم" -> "می‌کنم".
_ZWNJ_WORDS = {
    "میکنم", "میکنی", "میکند", "میکنیم", "میکنید", "میکنند",
    "میشوم", "میشوی", "میشود", "میشویم", "میشوید", "میشوند",
    "میگویم", "میگویی", "میگوید", "میگوییم", "میگویید", "میگویند",
    "میگم", "میگی", "میگه", "میگن",
    "میخواهم", "میخواهی", "میخواهد", "میخواهیم", "میخواهید", "میخواهند",
    "میخوام", "میخوای", "میخواد", "میخوان",
    "میدانم", "میدانی", "میداند", "میدانیم", "میدانید", "میدانند",
    "میدم", "میدی", "میده", "میدن",
    "میبرم", "میبری", "میبرد", "میبریم", "میبرید", "میبرند",
    "میرم", "میری", "میره", "میرن",
    "میروم", "میروی", "میرود", "میرویم", "میروید", "میروند",
    "میآیم", "میآیی", "میآید", "میآییم", "میآیید", "میآیند",
    "میشنوم", "میشنوی", "میشنود", "میشنویم", "میشنوید", "میشنوند",
    "میبینم", "میبینی", "میبیند", "میبینیم", "میبینید", "میبینند",
    "میشه",
    "نمیکنم", "نمیکنی", "نمیکند", "نمیکنیم", "نمیکنید", "نمیکنند",
    "نمیشود", "نمیشه",
    "نمیگویم", "نمیگم", "نمیگی", "نمیگه", "نمیگن",
    "نمیخواهم", "نمیخواهد", "نمیخوام", "نمیخواد",
    "نمیدانم", "نمیدانی", "نمیداند",
    "نمیدونم", "نمیدونی", "نمیدونه", "نمیدونن",
    "نمیدم", "نمیدی", "نمیده", "نمیدن",
    "نمیرم", "نمیری", "نمیره", "نمیرن", "نمیرود",
    "نمیآید", "نمیاد",
    "نمیبینم", "نمیبینی", "نمیبیند",
}

# The imperative "ب" is frequently mis-heard as the real word "بی" and
# emitted as its own token: "بپوش ببین" -> "بی پوش بی بین". Only
# unambiguous imperatives are repaired, and only right after "بی"/"به".
_SPLIT_IMPERATIVES = {
    "پوش": "بپوش",
    "بین": "ببین",
    "بینم": "ببینم",
    "بینی": "ببینی",
    "بینید": "ببینید",
    "بینند": "ببینند",
    "خواب": "بخواب",
    "خور": "بخور",
    "شین": "بشین",
    "نشین": "بنشین",
    "گیر": "بگیر",
    "گو": "بگو",
    "گوی": "بگو",
    "بخش": "ببخش",
}

# Separated ZWNJ prefixes: "می کنم" -> "می‌کنم" (fused with the next token).
_FUSED_PREFIXES = {
    "می کنم": "می‌کنم", "می کنی": "می‌کنی", "می کند": "می‌کند",
    "می کنیم": "می‌کنیم", "می کنید": "می‌کنید", "می کنند": "می‌کنند",
    "می شود": "می‌شود", "می شن": "می‌شن", "می شه": "می‌شه",
    "می گویم": "می‌گویم", "می گویی": "می‌گویی", "می گوید": "می‌گوید",
    "می گوییم": "می‌گوییم", "می گویید": "می‌گویید", "می گویند": "می‌گویند",
    "می گم": "می‌گم", "می گی": "می‌گی", "می گه": "می‌گه", "می گن": "می‌گن",
    "می خواهم": "می‌خواهم", "می خواهی": "می‌خواهی", "می خواهد": "می‌خواهد",
    "می خواهیم": "می‌خواهیم", "می خواهید": "می‌خواهید", "می خواهند": "می‌خواهند",
    "می خوام": "می‌خوام", "می خوای": "می‌خوای", "می خواد": "می‌خواد",
    "می دانم": "می‌دانم", "می دانی": "می‌دانی", "می داند": "می‌داند",
    "می دونم": "می‌دونم", "می دونی": "می‌دونی", "می دونه": "می‌دونه",
    "می دم": "می‌دم", "می دی": "می‌دی", "می ده": "می‌ده", "می دن": "می‌دن",
    "می برم": "می‌برم", "می برد": "می‌برد",
    "می رم": "می‌رم", "می ری": "می‌ری", "می ره": "می‌ره", "می رن": "می‌رن",
    "می روم": "می‌روم", "می رود": "می‌رود",
    "می آیم": "می‌آیم", "می آید": "می‌آید", "می این": "می‌این",
    "می شنوم": "می‌شنوم", "می شنوی": "می‌شنوی", "می شنود": "می‌شنود",
    "می بینم": "می‌بینم", "می بینی": "می‌بینی", "می بیند": "می‌بیند",
    "نمی کنم": "نمی‌کنم", "نمی کنی": "نمی‌کنی", "نمی کند": "نمی‌کند",
    "نمی شود": "نمی‌شود", "نمی شه": "نمی‌شه",
    "نمی گم": "نمی‌گم", "نمی گی": "نمی‌گی", "نمی گه": "نمی‌گه",
    "نمی خوام": "نمی‌خوام", "نمی خواد": "نمی‌خواد",
    "نمی دانم": "نمی‌دانم", "نمی داند": "نمی‌داند",
    "نمی دونم": "نمی‌دونم",
    "نمی رم": "نمی‌رم", "نمی ره": "نمی‌ره",
    "نمی آید": "نمی‌آید", "نمی این": "نمی‌این",
    "نمی بینم": "نمی‌بینم", "نمی بیند": "نمی‌بیند",
}

_PREFIX_TOKENS = ("می", "نمی")

# Separated ZWNJ suffixes: "پروانه های" -> "پروانه‌های" (fused with previous).
_SUFFIX_TOKENS = ("ها", "های", "هایی", "تر", "ترین")

# Punctuation marks that swallow the space BEFORE them (closing marks only —
# opening « and ( keep their leading space).
_CLOSING_PUNCT = "،؛:.!?؟…»)"

# ----------------------------------------------------------------- pipeline


def _fix_chars(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch in _ARABIC_CHARS:
            out.append(_ARABIC_CHARS[ch])
        elif ch in _LATIN_DIGITS:
            out.append(_LATIN_DIGITS[ch])
        else:
            out.append(ch)
    return "".join(out)


def _split_edges(token: str) -> tuple[str, str, str]:
    """Split a token into (leading punct, core, trailing punct)."""
    core = token.strip("،؛:.!?؟…«»()\"'-–—,")
    if not core:
        return token, "", ""
    start = token.index(core)
    return token[:start], core, token[start + len(core):]


def _zwnj_in_word(word: str) -> str:
    """Insert the ZWNJ after a leading می/نمی prefix inside one token."""
    if word.startswith("نمی") and len(word) > 3:
        return "نمی" + _ZWNJ + word[3:]
    if word.startswith("می") and len(word) > 2:
        return "می" + _ZWNJ + word[2:]
    return word


def _fix_tokens(text: str) -> str:
    tokens = text.split()
    fixed: list[str] = []
    for token in tokens:
        leading, core, trailing = _split_edges(token)
        if not core:
            fixed.append(token)
            continue
        if core in _ZWNJ_WORDS:
            core = _zwnj_in_word(core)
        fixed.append(leading + core + trailing)
    # Split-imperative repair needs the previous token, so run after folding.
    fused = _fuse(fixed)
    repaired: list[str] = []
    for token in fused.split():
        _leading, core, _trailing = _split_edges(token)
        if (
            core in _SPLIT_IMPERATIVES
            and repaired
            and repaired[-1].strip("،؛:.!?؟…«»()\"'-–—,") in ("بی", "به")
        ):
            repaired[-1] = _SPLIT_IMPERATIVES[core]
            continue
        repaired.append(token)
    return " ".join(repaired)


def _fuse(tokens: list[str]) -> str:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        bare = tok.strip("،؛:.!?؟…«»()\"'-–—,")
        if bare in _PREFIX_TOKENS and i + 1 < len(tokens):
            pair = f"{tok} {tokens[i + 1]}"
            fused = _FUSED_PREFIXES.get(pair)
            if fused is None and bare == tok:  # no punctuation on the prefix
                fused = tok + _ZWNJ + tokens[i + 1]
            if fused is not None:
                out.append(fused)
                i += 2
                continue
        if bare in _SUFFIX_TOKENS and out:
            prev = out[-1]
            prev_core = prev.strip("،؛:.!?؟…«»()\"'-–—,")
            if prev_core and prev_core[-1].isalpha():
                if bare == tok:  # no punctuation on the suffix itself
                    out[-1] = prev + _ZWNJ + bare
                else:
                    out[-1] = prev + _ZWNJ + bare
                i += 1
                continue
        out.append(tok)
        i += 1
    return " ".join(out)


def _fix_spacing(text: str) -> str:
    """No space before a closing mark, one space after (digit-safe)."""
    text = text.replace(_ZWNJ + " ", _ZWNJ).replace(" " + _ZWNJ, _ZWNJ)
    out: list[str] = []
    for i, ch in enumerate(text):
        if ch in _CLOSING_PUNCT and out and out[-1] == " ":
            out.pop()
        out.append(ch)
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch in _CLOSING_PUNCT and nxt and nxt not in _CLOSING_PUNCT and nxt != " ":
            # 3.5 / ۱۲٫۵ keep the dot glued to both digits
            if not (ch in ".،" and out[-2:-1] and out[-2].isdigit() and nxt.isdigit()):
                out.append(" ")
    return "".join(out)


def polish_transcript(text: str) -> str:
    """Repair Persian ASR orthography without rewording. Deterministic."""
    if not text or not text.strip():
        return text
    polished = _fix_chars(text)
    polished = _fix_tokens(polished)
    polished = _fix_spacing(polished)
    return polished.strip()
