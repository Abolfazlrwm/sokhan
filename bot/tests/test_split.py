from sokhan_bot.split import split_message


def test_short_text_stays_one_chunk():
    assert split_message("سلام بر تو") == ["سلام بر تو"]


def test_empty_text_returns_no_chunks():
    assert split_message("   ") == []


def test_long_text_splits_under_limit():
    paragraph = "این یک پاراگراف آزمایشی نسبتاً طولانی است. " * 120
    text = "\n\n".join(paragraph for _ in range(5))

    chunks = split_message(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= 3900 for chunk in chunks)
    # Each chunk becomes its own Telegram message; boundary whitespace may be
    # stripped, but no word may be split in half.
    assert " ".join(chunks).split() == text.split()


def test_hard_cut_without_separators():
    # "الف" is three characters, so this text is 15000 characters long.
    text = "الف" * 5000

    chunks = split_message(text)

    assert len(chunks) == 4
    assert all(len(chunk) <= 3900 for chunk in chunks)
    assert "".join(chunks) == text


def test_custom_limit_respected():
    text = "یکی دو سه چهار پنج شش هفت هشت نه ده"

    chunks = split_message(text, limit=12)

    assert all(len(chunk) <= 12 for chunk in chunks)
    assert len(chunks) >= 2
