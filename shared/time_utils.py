"""Timezone-aware KST helpers and the default seven-day scout window."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
DEFAULT_LOOKBACK_DAYS = 7


def now_kst() -> datetime:
    return datetime.now(tz=KST)


def ensure_kst(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(KST)


def parse_iso_kst(value: str) -> datetime:
    return ensure_kst(datetime.fromisoformat(value.replace("Z", "+00:00")))


def kst_day_bounds(value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min, tzinfo=KST)
    return start, start + timedelta(days=1)


def recent_window(*, now: datetime | None = None, days: int = DEFAULT_LOOKBACK_DAYS) -> tuple[datetime, datetime]:
    if days <= 0:
        raise ValueError("days must be positive")
    end = ensure_kst(now) if now is not None else now_kst()
    return end - timedelta(days=days), end


def is_recent(value: datetime, *, now: datetime | None = None, days: int = DEFAULT_LOOKBACK_DAYS) -> bool:
    start, end = recent_window(now=now, days=days)
    return start <= ensure_kst(value) <= end
