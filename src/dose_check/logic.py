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


DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
ALL_DAYS = "0,1,2,3,4,5,6"
_DAY_PREFIX = {name[:3]: index for index, name in enumerate(DAY_NAMES)}
_DAY_PREFIX["tues"] = 1
_DAY_PREFIX["thur"] = 3
_DAY_PREFIX["thurs"] = 3


def parse_days(text: str) -> list[int] | None:
    """Turn 'mon,wed,fri', 'weekdays', 'daily' or '0,2,4' into weekday numbers (Monday is 0).

    Returns None when nothing was said about days, and [] when the words were not understood.
    """
    folded = text.strip().lower()
    if not folded:
        return None
    if re.search(r"\b(?:daily|every ?day|all days|everyday|each day)\b", folded):
        return list(range(7))
    days: set[int] = set()
    if re.search(r"\bweek ?days?\b", folded):
        days.update(range(5))
    if re.search(r"\bweek ?ends?\b", folded):
        days.update((5, 6))
    for start, end in re.findall(r"\b([a-z]+)\s*(?:to|through|thru|-)\s*([a-z]+)\b", folded):
        first, last = _DAY_PREFIX.get(start[:4] if start[:4] in _DAY_PREFIX else start[:3]), _DAY_PREFIX.get(end[:4] if end[:4] in _DAY_PREFIX else end[:3])
        if first is not None and last is not None:
            index = first
            while True:
                days.add(index)
                if index == last:
                    break
                index = (index + 1) % 7
    for token in re.findall(r"[a-z]+|\d", folded):
        if token.isdigit():
            if 0 <= int(token) <= 6:
                days.add(int(token))
            continue
        if token in ("weekday", "weekdays", "weekend", "weekends", "to", "through", "thru", "and", "on", "every", "each"):
            continue
        key = token.rstrip("s") if token.rstrip("s") in DAY_NAMES else token
        if key in DAY_NAMES:
            days.add(DAY_NAMES.index(key))
        elif key in _DAY_PREFIX and len(key) >= 3:
            days.add(_DAY_PREFIX[key])
    return sorted(days)


def days_to_str(days: list[int]) -> str:
    return ",".join(str(day) for day in sorted(set(days)))


def days_from_str(value: str | None) -> list[int]:
    if not value:
        return list(range(7))
    return sorted(int(part) for part in value.split(",") if part.strip().isdigit())


def speak_days(days: list[int]) -> str:
    days = sorted(set(days))
    if days == list(range(7)):
        return "every day"
    if days == [0, 1, 2, 3, 4]:
        return "on weekdays"
    if days == [5, 6]:
        return "on weekends"
    names = [DAY_NAMES[day].capitalize() for day in days]
    if len(names) == 1:
        return f"on {names[0]}s"
    return "on " + ", ".join(names[:-1]) + f" and {names[-1]}"


def day_matches(days: list[int], day_iso: str) -> bool:
    year, month, day = (int(part) for part in day_iso.split("-"))
    return datetime(year, month, day).weekday() in days
