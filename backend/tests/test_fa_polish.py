"""fa_polish: orthographic Persian ASR repair — deterministic and safe.

The polisher may only repair surface orthography. It must never change
which words a sentence contains (beyond fusing tokens that belong behind
one ZWNJ), because the same function runs on both sides of the WER
benchmark and inside the product pipeline.
"""

from sokhan.core.fa_polish import polish_transcript


def test_zwnj_prefix_fusion():
    assert polish_transcript("تو من رو مامنو می کنی؟") == "تو من رو مامنو می‌کنی؟"


def test_zwnj_inside_single_token():
    assert polish_transcript("نمیدونم چی میخواد") == "نمی‌دونم چی می‌خواد"


def test_suffix_fusion():
    assert (
        polish_transcript("پروانه های کوپی لفت را به وجود اورد")
        == "پروانه‌های کوپی لفت را به وجود اورد"
    )


def test_split_imperative_repair():
    assert polish_transcript("میگه بی پوش بی بین اندازت هست") == "می‌گه بپوش ببین اندازت هست"


def test_standalone_bei_is_untouched():
    # "بی" is a real word ("without"); only imperative pairs are repaired.
    assert polish_transcript("بی پول نمی ره") == "بی پول نمی‌ره"


def test_arabic_chars_and_digits():
    assert polish_transcript("سلام 3 ساعته 2024") == "سلام ۳ ساعته ۲۰۲۴"


def test_decimal_point_stays_glued():
    assert polish_transcript("قیمت 3.5 تومن شد") == "قیمت ۳.۵ تومن شد"


def test_no_space_before_closing_mark():
    assert polish_transcript("حالا چی ؟") == "حالا چی؟"


def test_idempotent():
    once = polish_transcript("میگه بی پوش بی بین اندازت هست")
    assert polish_transcript(once) == once


def test_never_rewords():
    # Acoustic mishears pass through untouched — polish is not a rewriter.
    src = "و سیار خوبین آلیر"
    assert polish_transcript(src) == src


def test_empty_and_whitespace_safe():
    assert polish_transcript("") == ""
    assert polish_transcript("   ") == "   "
