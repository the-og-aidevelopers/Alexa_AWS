"""Due, overdue, and spoken-time rules. No database and no network."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

GRACE = timedelta(minutes=30)
LEAD = timedelta(minutes=90)

_WINDOWS = {
    "morning": (5 * 60, 12 * 60),
    "afternoon": (12 * 60, 17 * 60),
    "evening": (17 * 60, 21 * 60),
    "night": (21 * 60, 24 * 60),
    "tonight": (17 * 60, 24 * 60),
}


def local_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now().astimezone()
    if now.tzinfo is None:
        return now.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return now


def speak_time(hhmm: str) -> str:
    hour, minute = (int(part) for part in hhmm.split(":"))
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    if minute == 0:
        return f"{hour12} {suffix}"
    return f"{hour12}:{minute:02d} {suffix}"


def scheduled_at(day_iso: str, hhmm: str, tzinfo: datetime.tzinfo) -> datetime:
    year, month, day = (int(part) for part in day_iso.split("-"))
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(year, month, day, hour, minute, tzinfo=tzinfo)


def dose_state(scheduled: datetime, now: datetime, log: dict[str, Any] | None) -> str:
    if log:
        return str(log["status"])
    if now > scheduled + GRACE:
        return "overdue"
    if now >= scheduled - LEAD:
        return "due"
    return "upcoming"


def minutes_late(scheduled: datetime, now: datetime) -> int:
    late = now - (scheduled + GRACE)
    if late.total_seconds() <= 0:
        return 0
    return int(late.total_seconds() // 60)


def time_matches(hhmm: str, hint: str) -> bool:
    hint = hint.strip().lower()
    if re.fullmatch(r"\d{2}:\d{2}", hint):
        return hhmm == hint
    if hint not in _WINDOWS:
        return False
    hour, minute = (int(part) for part in hhmm.split(":"))
    start, end = _WINDOWS[hint]
    return start <= (hour * 60 + minute) < end


def valid_clock(value: str) -> bool:
    return re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value) is not None
