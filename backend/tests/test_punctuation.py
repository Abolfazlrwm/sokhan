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


# Edge cases from #30. Each test pins the behavior on real-world input; the
# comments say why that behavior is the right one for a transcript.


def test_slash_dates_are_left_intact():
    # `/` is not punctuation to this pass, so date groups never get spaced
    # or split, in Persian and in Latin digits alike.
    assert restore_punctuation("تاریخ ۱۴۰۴/۰۹/۰۲ است") == "تاریخ ۱۴۰۴/۰۹/۰۲ است."
    assert restore_punctuation("جلسه 2026/11/23 برگزار شد") == "جلسه 2026/11/23 برگزار شد."
    assert restore_punctuation("نسبت ۱/۲ است") == "نسبت ۱/۲ است."


def test_latin_digits_and_words_inside_persian_sentences():
    assert restore_punctuation("۳ دستگاه RTX 4090 خریدیم") == "۳ دستگاه RTX 4090 خریدیم."
    assert restore_punctuation("قیمت ۳.۵ میلیون شد") == "قیمت ۳.۵ میلیون شد."
    assert restore_punctuation("نسخه 1.4.1 منتشر شد") == "نسخه 1.4.1 منتشر شد."
    assert restore_punctuation("ساعت ۱۲:۳۰ بیا") == "ساعت ۱۲:۳۰ بیا."


def test_thousands_separators_are_not_turned_into_persian_commas():
    # A Latin comma followed by exactly three digits groups a number; turning
    # it into ، and spacing it ("1، 000") would split one number into two.
    assert restore_punctuation("قیمت 1,000 دلار شد") == "قیمت 1,000 دلار شد."
    assert restore_punctuation("جمعیت 12,500,000 نفر") == "جمعیت 12,500,000 نفر."
    assert restore_punctuation("مبلغ ۱,۲۰۰ تومان") == "مبلغ ۱,۲۰۰ تومان."


def test_comma_between_numbers_that_is_not_grouping_stays_a_list_separator():
    assert restore_punctuation("RTX 4090,4080 و 3090") == "RTX 4090، 4080 و 3090."
    assert restore_punctuation("اعداد 1,2 و 3") == "اعداد 1، 2 و 3."


def test_abbreviation_dots_are_kept_and_end_the_segment():
    # A trailing dot already counts as terminal punctuation, so nothing is
    # appended; a dot in the middle is left alone like a decimal point.
    assert restore_punctuation("Dr.") == "Dr."
    assert restore_punctuation("با Dr. Smith صحبت کردم") == "با Dr. Smith صحبت کردم."
    assert restore_punctuation("با دکتر. احمدی") == "با دکتر. احمدی."


def test_ellipsis_forms_are_terminal_and_tightened():
    assert restore_punctuation("صبر کن…") == "صبر کن…"
    assert restore_punctuation("نمیدونم...") == "نمیدونم..."
    assert restore_punctuation("صبر کن ... بعد") == "صبر کن... بعد."
    # A trailing-off question keeps its ellipsis instead of gaining a ؟.
    assert restore_punctuation("کی میای...") == "کی میای..."


def test_repeated_and_mixed_marks_are_preserved():
    # Repetition carries the speaker's emphasis; the pass only converts the
    # script of Latin marks and never collapses them.
    assert restore_punctuation("وای!!!") == "وای!!!"
    assert restore_punctuation("چرا!!!") == "چرا!!!"
    assert restore_punctuation("چی؟؟") == "چی؟؟"
    assert restore_punctuation("واقعا?!") == "واقعا؟!"
