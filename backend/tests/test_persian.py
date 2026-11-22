from sokhan.core.persian import normalize_for_search, normalize_persian, strip_punctuation


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


def test_strip_punctuation_replaces_marks_with_spaces():
    assert strip_punctuation("سلام، حالت") == "سلام  حالت"
    assert strip_punctuation("چطوره؟ خوبم.") == "چطوره  خوبم "


def test_normalize_for_search_collapses_punctuation_and_whitespace():
    assert normalize_for_search("سلام، حالت چطوره؟") == "سلام حالت چطوره"


def test_normalize_for_search_matches_unpunctuated_query():
    punctuated = normalize_for_search("حالت، چطوره؟")
    assert normalize_for_search("حالت چطوره") == punctuated


def test_normalize_persian_keeps_punctuation_for_benchmark_compatibility():
    # The WER benchmark normalizes with normalize_persian only; it must not
    # change behaviour now that search has its own punctuation-aware variant.
    assert normalize_persian("سلام، حالت؟") == "سلام، حالت؟"
