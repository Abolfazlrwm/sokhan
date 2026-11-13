import pytest
from sokhan.core.quota import (
    QuotaExceededError,
    ensure_quota,
    get_quota_info,
    month_key,
    month_start,
    record_usage,
    used_seconds_in_month,
)
from sokhan.db import session_scope
from sokhan.models import Usage, utcnow


def test_month_key_and_start():
    moment = utcnow().replace(year=2026, month=11, day=13, hour=15, minute=30)
    assert month_key(moment) == "2026-11"
    start = month_start(moment)
    assert start.day == 1
    assert start.hour == 0
    assert start.minute == 0


def test_quota_counts_only_current_month(app, seeded_user):
    moment = utcnow()
    last_month = moment.replace(month=max(1, moment.month - 1))
    with session_scope() as session:
        session.add(Usage(user_id=seeded_user["id"], job_id=None, seconds=600))
        session.add(Usage(user_id=seeded_user["id"], job_id=None, seconds=300))
        if last_month.month != moment.month:
            stale = Usage(user_id=seeded_user["id"], job_id=None, seconds=600)
            stale.created_at = last_month
            session.add(stale)

    with session_scope() as session:
        used = used_seconds_in_month(session, seeded_user["id"], moment)
    assert used == pytest.approx(900.0)


def test_ensure_quota_passes_under_limit(app, seeded_user):
    moment = utcnow()
    with session_scope() as session:
        session.add(Usage(user_id=seeded_user["id"], job_id=None, seconds=29 * 60))

    with session_scope() as session:
        info = ensure_quota(session, seeded_user["id"], moment, limit_minutes=30)
    assert info.used_minutes == pytest.approx(29.0)
    assert info.remaining_minutes == pytest.approx(1.0)


def test_ensure_quota_raises_over_limit(app, seeded_user):
    moment = utcnow()
    with session_scope() as session:
        session.add(Usage(user_id=seeded_user["id"], job_id=None, seconds=30 * 60))

    with session_scope() as session:
        with pytest.raises(QuotaExceededError) as excinfo:
            ensure_quota(session, seeded_user["id"], moment, limit_minutes=30)
    assert excinfo.value.limit_minutes == 30


def test_quota_info_never_negative(app, seeded_user):
    moment = utcnow()
    with session_scope() as session:
        session.add(Usage(user_id=seeded_user["id"], job_id=None, seconds=45 * 60))

    with session_scope() as session:
        info = get_quota_info(session, seeded_user["id"], moment, limit_minutes=30)
    assert info.remaining_minutes == 0.0


def test_record_usage_appends(app, seeded_user):
    with session_scope() as session:
        record_usage(session, seeded_user["id"], None, 12.5)

    with session_scope() as session:
        assert used_seconds_in_month(session, seeded_user["id"], utcnow()) == pytest.approx(12.5)
