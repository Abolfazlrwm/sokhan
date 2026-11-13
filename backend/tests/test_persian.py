from sokhan.core.persian import normalize_persian


def test_arabic_yeh_and_kaf_map_to_persian():
    assert normalize_persian("يك") == "یک"


def test_alef_variants_collapse():
    assert normalize_persian("أآإا") == "اااا"


def test_zwnj_and_tatweel_removed():
    assert normalize_persian("می\u200cرود") == "میرود"
    assert normalize_persian("ســلام") == "سلام"


def test_latin_lowercased():
    assert normalize_persian("Meeting") == "meeting"


def test_normalize_is_idempotent():
    once = normalize_persian("كتاب\u200cها")
    assert once == normalize_persian(once)
