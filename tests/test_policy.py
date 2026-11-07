from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from policy import (
    State,
    record_attempt,
    record_failure,
    record_success,
    should_fetch,
    stats,
    target_day,
)

PT = ZoneInfo("US/Pacific")


def t(y, mo, d, h=0, mi=45):
    return datetime(y, mo, d, h, mi, tzinfo=PT)


def test_target_is_previous_local_day():
    assert target_day(t(2026, 11, 6, 0, 45)) == date(2026, 11, 5)
    assert target_day(t(2026, 11, 1, 23, 59)) == date(2026, 10, 31)  # DST end day


def test_fetch_once_then_skip_until_rollover():
    st = State()
    now = t(2026, 11, 6)
    assert should_fetch(st, now)
    record_attempt(st, now)
    record_success(st, now, date(2026, 11, 5), {"a-1": 1.0})
    assert not should_fetch(st, now)                     # duplicate refresh
    assert not should_fetch(st, t(2026, 11, 6, 23, 0))   # restart same day
    assert should_fetch(st, t(2026, 11, 7))              # rollover


def test_attempt_cap_survives_restarts():
    st = State()
    for i in range(3):
        now = t(2026, 11, 6, 1 + i)
        assert should_fetch(st, now)
        record_attempt(st, now)
        record_failure(st, now, "timeout", limit=False)
        st = State.from_dict(st.to_dict())               # persisted round-trip
    assert not should_fetch(st, t(2026, 11, 6, 9))
    assert should_fetch(st, t(2026, 11, 7))              # new target resets


def test_limit_backoff_24h_blocks_manual_too():
    st = State()
    now = t(2026, 11, 6)
    record_attempt(st, now)
    record_failure(st, now, "limit", limit=True)
    assert not should_fetch(st, now + timedelta(hours=23))
    assert not should_fetch(st, now + timedelta(hours=1), manual=True)
    assert should_fetch(st, now + timedelta(hours=25))


def test_manual_throttle():
    st = State()
    now = t(2026, 11, 6, 12)
    assert should_fetch(st, now, manual=True)
    record_attempt(st, now, manual=True)
    assert not should_fetch(st, now + timedelta(minutes=5), manual=True)
    assert should_fetch(st, now + timedelta(minutes=16), manual=True)


def test_state_from_corrupt_dict():
    st = State.from_dict({"channels": "x", "unknown": 1})
    assert st.channels == {} and st.data_date is None


def test_stats():
    assert stats({}) == {}
    s = stats({"a-1": 1.0, "a-2": 1.2, "b-1": 0.8})
    assert s == {"total": 3.0, "mean": 1.0, "spread_pct": 40.0, "count": 3}
    assert stats({"a-1": 0.0})["spread_pct"] is None
