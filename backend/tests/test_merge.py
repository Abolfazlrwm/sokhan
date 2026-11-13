from sokhan.core.merge import merge_chunks, offset_segments
from sokhan.core.transcribe import Segment


def test_offset_segments_shifts_times():
    shifted = offset_segments([Segment(start=0, end=1, text="سلام", avg_logprob=-0.1)], 30)
    assert shifted[0].start == 30
    assert shifted[0].end == 31
    assert shifted[0].text == "سلام"


def test_merge_drops_boundary_duplicate():
    left = Segment(start=28.0, end=29.9, text="متن آزمایشی طولانی برای تست", avg_logprob=-0.2)
    duplicate = Segment(start=0.5, end=2.0, text="متن آزمایشی طولانی برای تست", avg_logprob=-0.9)
    tail = Segment(start=2.5, end=4.0, text="ادامه گفتار", avg_logprob=-0.3)
    merged = merge_chunks([[left], [duplicate, tail]], [0.0, 29.0], overlap_seconds=1.0)

    assert [segment.text for segment in merged] == ["متن آزمایشی طولانی برای تست", "ادامه گفتار"]
    assert merged[0].start == 28.0
    assert merged[1].start == 31.5


def test_merge_keeps_higher_confidence_duplicate():
    left = Segment(start=28.0, end=29.9, text="متن آزمایشی طولانی برای تست", avg_logprob=-0.9)
    duplicate = Segment(start=0.5, end=2.0, text="متن آزمایشی طولانی برای تست", avg_logprob=-0.2)
    merged = merge_chunks([[left], [duplicate]], [0.0, 29.0], overlap_seconds=1.0)

    assert len(merged) == 1
    assert merged[0].start == 29.5
    assert merged[0].avg_logprob == -0.2


def test_merge_keeps_dissimilar_boundary_segments():
    left = Segment(start=28.5, end=29.9, text="جمله اول گفتار", avg_logprob=-0.2)
    fresh = Segment(start=0.2, end=1.8, text="مطلب تازه آغاز می‌شود", avg_logprob=-0.3)
    merged = merge_chunks([[left], [fresh]], [0.0, 29.0], overlap_seconds=1.0)

    assert len(merged) == 2


def test_merge_clamps_overflowing_and_negative_times():
    negative = Segment(start=-0.3, end=0.5, text="شروع", avg_logprob=-0.1)
    overflowing = Segment(start=9.0, end=10.5, text="پایان", avg_logprob=-0.1)
    merged = merge_chunks([[negative, overflowing]], [0.0], 0.0, total_duration=10.0)

    assert merged[0].start == 0.0
    assert merged[1].end == 10.0


def test_merge_sorts_segments_by_start():
    late = Segment(start=20.0, end=21.0, text="دیر", avg_logprob=-0.1)
    early = Segment(start=1.0, end=2.0, text="زود", avg_logprob=-0.1)
    merged = merge_chunks([[late, early]], [0.0], 0.0)

    assert [segment.text for segment in merged] == ["زود", "دیر"]
