"""Pure scheduling/backoff policy and persisted state (no HA imports)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

try:
    from .const import LIMIT_BACKOFF_HOURS, MANUAL_MIN_INTERVAL_MIN, MAX_ATTEMPTS_PER_DAY
except ImportError:
    from const import LIMIT_BACKOFF_HOURS, MANUAL_MIN_INTERVAL_MIN, MAX_ATTEMPTS_PER_DAY  # type: ignore


def target_day(now_local: datetime) -> date:
    """The most recent completed local day."""
    return now_local.date() - timedelta(days=1)


@dataclass
class State:
    data_date: str | None = None
    channels: dict[str, float] = field(default_factory=dict)
    fetched_at: str | None = None
    attempts_date: str | None = None
    attempts: int = 0
    backoff_until: str | None = None
    last_manual: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict | None) -> "State":
        s = cls()
        for k, v in (d or {}).items():
            if hasattr(s, k):
                setattr(s, k, v)
        if not isinstance(s.channels, dict):
            s.channels = {}
        return s


def should_fetch(st: State, now: datetime, manual: bool = False) -> bool:
    """Decide whether an API call is allowed now (now must be tz-aware local)."""
    if st.backoff_until and now < datetime.fromisoformat(st.backoff_until):
        return False
    if manual:
        if st.last_manual and now - datetime.fromisoformat(st.last_manual) < \
                timedelta(minutes=MANUAL_MIN_INTERVAL_MIN):
            return False
        return True
    tgt = target_day(now).isoformat()
    if st.data_date == tgt:
        return False
    if st.attempts_date == tgt and st.attempts >= MAX_ATTEMPTS_PER_DAY:
        return False
    return True


def record_attempt(st: State, now: datetime, manual: bool = False) -> None:
    tgt = target_day(now).isoformat()
    if st.attempts_date != tgt:
        st.attempts_date, st.attempts = tgt, 0
    st.attempts += 1
    if manual:
        st.last_manual = now.isoformat()


def record_success(st: State, now: datetime, day: date,
                   channels: dict[str, float]) -> None:
    st.data_date = day.isoformat()
    st.channels = dict(channels)
    st.fetched_at = now.isoformat()
    st.backoff_until = None
    st.last_error = None


def record_failure(st: State, now: datetime, error: str, limit: bool) -> None:
    st.last_error = error
    if limit:
        st.backoff_until = (now + timedelta(hours=LIMIT_BACKOFF_HOURS)).isoformat()


def stats(channels: dict[str, float]) -> dict:
    """Total, mean and spread ((max-min)/mean %) of channel kWh."""
    if not channels:
        return {}
    vals = list(channels.values())
    total = sum(vals)
    mean = total / len(vals)
    spread = (max(vals) - min(vals)) / mean * 100 if mean > 0 else None
    return {"total": round(total, 3), "mean": round(mean, 3),
            "spread_pct": None if spread is None else round(spread, 1),
            "count": len(vals)}
