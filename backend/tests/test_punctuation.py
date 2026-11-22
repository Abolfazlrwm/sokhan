from sokhan.core.punctuation import restore_punctuation


def test_declarative_segment_gets_a_period():
    assert restore_punctuation("سلام بر تو") == "سلام بر تو."


def test_question_word_triggers_a_question_mark():
    assert restore_punctuation("حالت چطور است") == "حالت چطور است؟"
    assert restore_punctuation("کیه اینجا") == "کیه اینجا؟"
    assert restore_punctuation("کجا می‌روی") == "کجا می‌روی؟"


def test_آیا_counts_as_a_question():
    assert restore_punctuation("آیا آماده‌ای") == "آیا آماده‌ای؟"


def test_existing_terminal_punctuation_is_left_alone():
    assert restore_punctuation("حالت چطور است؟") == "حالت چطور است؟"
    assert restore_punctuation("متشکرم!") == "متشکرم!"
    assert restore_punctuation("صبر کن…") == "صبر کن…"


def test_latin_punctuation_becomes_persian():
    assert restore_punctuation("اول این, بعد آن; فکر کن?") == "اول این، بعد آن؛ فکر کن؟"


def test_spacing_is_fixed_around_punctuation():
    assert restore_punctuation("سلام ، دنیا") == "سلام، دنیا."
    assert restore_punctuation("سلام,دنیا") == "سلام، دنیا."
    assert restore_punctuation("بله . حالت چطوره ؟") == "بله. حالت چطوره؟"


def test_decimals_and_times_survive():
    assert restore_punctuation("قیمتش 3.5 شد") == "قیمتش 3.5 شد."
    assert restore_punctuation("ساعت 12:30 بده") == "ساعت 12:30 بده."


def test_is_idempotent():
    once = restore_punctuation("حالت چطوره")
    assert restore_punctuation(once) == once
    twice = restore_punctuation("سلام، دنیا.")
    assert restore_punctuation(twice) == twice


def test_empty_and_whitespace_input_stay_empty():
    assert restore_punctuation("") == ""
    assert restore_punctuation("   ") == ""


def test_statement_with_colon_gets_no_double_mark():
    assert restore_punctuation("این است") == "این است."
    assert restore_punctuation("این است:") == "این است:"
