import io

from docx import Document
from sokhan.core.formats import format_srt_timestamp, to_docx, to_srt, to_txt
from sokhan.core.transcribe import Segment


def test_srt_timestamp_formatting():
    assert format_srt_timestamp(0) == "00:00:00,000"
    assert format_srt_timestamp(3661.5) == "01:01:01,500"
    assert format_srt_timestamp(65.123) == "00:01:05,123"
    assert format_srt_timestamp(-3) == "00:00:00,000"


def test_srt_blocks_are_numbered_and_ordered():
    segments = [Segment(start=0, end=1.5, text="سلام"), Segment(start=2, end=4, text="خداحافظ")]
    srt = to_srt(segments)

    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,500\nسلام")
    assert "2\n00:00:02,000 --> 00:00:04,000\nخداحافظ" in srt


def test_srt_marks_speaker_when_present():
    srt = to_srt([Segment(start=0, end=1, text="متن", speaker="spk_1")])
    assert "[spk_1]" in srt


def test_txt_joins_segments_with_newlines():
    assert to_txt([Segment(start=0, end=1, text="الف"), Segment(start=1, end=2, text="ب")]) == "الف\nب"


def test_docx_contains_title_and_segments():
    data = to_docx(
        [Segment(start=0, end=1.5, text="سلام بر تو"), Segment(start=2, end=4, text="حالت چطور است")],
        title="جلسه هفته",
    )
    document = Document(io.BytesIO(data))
    texts = [paragraph.text for paragraph in document.paragraphs]

    assert texts[0] == "جلسه هفته"
    assert any("سلام بر تو" in text for text in texts)
    assert any("حالت چطور است" in text for text in texts)
