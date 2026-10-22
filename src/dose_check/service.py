"""Dose tools. Answers come from the schedule and the log, not from a model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from dose_check.db import Store
from dose_check.logic import (
    ALL_DAYS,
    day_matches,
    days_from_str,
    days_to_str,
    dose_state,
    local_now,
    minutes_late,
    scheduled_at,
    parse_days,
    speak_days,
    speak_time,
    time_matches,
    valid_clock,
)

OPEN_STATES = {"due", "overdue"}


def today_board(store: Store, now: datetime | None = None) -> dict[str, Any]:
    moment = local_now(now)
    day = moment.date().isoformat()
    doses = [_present(store, row, day, moment) for row in _rows_today(store, day)]
    alerts = [dose for dose in doses if dose["state"] == "overdue"]
    return {
        "day": day,
        "now": moment.isoformat(timespec="seconds"),
        "doses": doses,
        "alerts": alerts,
        "people": store.list_people(),
        "schedules": [_describe(row) for row in store.list_schedules()],
    }


def _rows_today(store: Store, day: str) -> list[dict[str, Any]]:
    return [row for row in store.list_schedules() if day_matches(days_from_str(row.get("days")), day)]


def _describe(row: dict[str, Any]) -> dict[str, Any]:
    days = days_from_str(row.get("days"))
    return {
        "schedule_id": int(row["id"]),
        "person_name": row["person_name"],
        "dose_label": row["dose_label"],
        "time_local": row["time_local"],
        "time_spoken": speak_time(row["time_local"]),
        "days": days,
        "days_spoken": speak_days(days),
    }


def list_due_doses(store: Store, person_name: str = "", now: datetime | None = None) -> dict[str, Any]:
    board = today_board(store, now)
    doses = _filter_person(board["doses"], person_name)
    due = [dose for dose in doses if dose["state"] == "due"]
    overdue = [dose for dose in doses if dose["state"] == "overdue"]
    upcoming = [dose for dose in doses if dose["state"] == "upcoming"]
    nxt = upcoming[0] if upcoming else None
    return {
        "ok": True,
        "due": due,
        "overdue": overdue,
        "next": nxt,
        "alerts": overdue,
        "speech": _speak_due(due, overdue, nxt),
    }


def log_dose(
    store: Store,
    status: str,
    person_name: str = "",
    dose_label: str = "",
    time_hint: str = "",
    reason: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    if status not in {"taken", "skipped"}:
        return {"ok": False, "speech": "A dose can be logged as taken or skipped.", "alerts": []}
    if not person_name.strip() and len(store.list_people()) > 1:
        return {"ok": False, "speech": "Please say whose dose this is, including their name.", "alerts": today_board(store, now)["alerts"]}
    moment = local_now(now)
    day = moment.date().isoformat()
    matches = _filter_rows(_rows_today(store, day), person_name, dose_label, time_hint)
    if not matches:
        board = today_board(store, moment)
        return {
            "ok": False,
            "speech": "I couldn't find that dose on today's schedule.",
            "alerts": board["alerts"],
        }
    presented = [_present(store, row, day, moment) for row in matches]
    chosen = _choose_for_log(presented, time_hint or dose_label or person_name)
    if chosen is None:
        board = today_board(store, moment)
        options = ", ".join(f"{dose['dose_label']} at {dose['time_spoken']}" for dose in presented)
        return {
            "ok": False,
            "speech": f"I found more than one dose: {options}. Say the medicine name or the time.",
            "alerts": board["alerts"],
        }
    note = reason.strip() if status == "skipped" else ""
    store.upsert_log(
        int(chosen["schedule_id"]),
        day,
        status,
        note,
        moment.isoformat(timespec="seconds"),
    )
    board = today_board(store, moment)
    logged = next(dose for dose in board["doses"] if dose["schedule_id"] == chosen["schedule_id"])
    return {"ok": True, "dose": logged, "alerts": board["alerts"], "speech": _speak_log(logged)}


def dose_status(
    store: Store,
    person_name: str = "",
    dose_label: str = "",
    time_hint: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    moment = local_now(now)
    day = moment.date().isoformat()
    rows = _filter_rows(_rows_today(store, day), person_name, dose_label, time_hint)
    if not rows:
        board = today_board(store, moment)
        if person_name.strip() and _filter_rows(store.list_schedules(), person_name, dose_label, ""):
            return {
                "ok": True,
                "doses": [],
                "alerts": board["alerts"],
                "speech": f"{person_name.strip().title()} has no doses scheduled today.",
            }
        known = store.find_person(person_name) if person_name.strip() else None
        if known and not dose_label.strip() and not time_hint.strip():
            return {"ok": True, "doses": [], "alerts": board["alerts"], "speech": f"{known} has no medicines yet."}
        return {
            "ok": False,
            "speech": "I couldn't find that dose on today's schedule.",
            "alerts": board["alerts"],
        }
    doses = [_present(store, row, day, moment) for row in rows]
    board = today_board(store, moment)
    return {
        "ok": True,
        "doses": doses,
        "alerts": board["alerts"],
        "speech": " ".join(_speak_status(dose) for dose in doses),
    }


def summarize_day(store: Store, person_name: str = "", now: datetime | None = None) -> dict[str, Any]:
    board = today_board(store, now)
    doses = _filter_person(board["doses"], person_name)
    counts = {state: 0 for state in ("taken", "skipped", "due", "overdue", "upcoming")}
    for dose in doses:
        counts[dose["state"]] = counts.get(dose["state"], 0) + 1
    ordered = sorted(doses, key=lambda dose: (dose["time_local"], dose["person_name"]))
    speech = " ".join(_speak_summary(dose) for dose in ordered) if ordered else "No doses are scheduled today."
    return {"ok": True, "counts": counts, "doses": doses, "alerts": board["alerts"], "speech": speech}


def _tidy_name(name: str) -> str:
    """Speech and models often return a lower-case name; show it capitalised."""
    cleaned = " ".join(name.split())
    return cleaned.title() if cleaned.islower() else cleaned


REMINDER_LEAD_MINUTES = 10


def upcoming_reminders(
    store: Store, lead_minutes: int = REMINDER_LEAD_MINUTES, now: datetime | None = None
) -> dict[str, Any]:
    """Doses that start within the next `lead_minutes` and are not logged yet, worded for speaking.

    This is what a smart speaker would announce a few minutes ahead, for example
    "Mom's lisinopril is due at 8 AM, in 10 minutes."
    """
    moment = local_now(now)
    day = moment.date().isoformat()
    reminders = []
    for dose in sorted(today_board(store, moment)["doses"], key=lambda d: (d["time_local"], d["person_name"])):
        if dose["state"] not in {"upcoming", "due"}:  # not logged yet; "due" opens 90 minutes ahead
            continue
        seconds = (scheduled_at(day, dose["time_local"], moment.tzinfo) - moment).total_seconds()
        minutes = int(-(-seconds // 60))  # round up, so 9m30s reads as 10 minutes
        if not 0 < minutes <= lead_minutes:
            continue
        unit = "minute" if minutes == 1 else "minutes"
        what = dose["dose_label"] if dose["dose_label"].lower() != "medicine" else "medicine"
        reminders.append({
            "schedule_id": dose["schedule_id"],
            "person_name": dose["person_name"],
            "dose_label": dose["dose_label"],
            "time_spoken": dose["time_spoken"],
            "minutes_until": minutes,
            "speech": f"{dose['person_name']}'s {what} is due at {dose['time_spoken']}, in {minutes} {unit}.",
        })
    return {"ok": True, "reminders": reminders, "speech": " ".join(item["speech"] for item in reminders)}


def register_person(store: Store, name: str) -> dict[str, Any]:
    cleaned = _tidy_name(name)
    if not cleaned:
        return {"ok": False, "speech": "Say the name to register, for example register him as Raj."}
    saved = store.add_person(cleaned)
    if not saved["created"]:
        return {
            "ok": True,
            "person_name": saved["name"],
            "speech": f"{saved['name']} is already registered.",
            "alerts": today_board(store)["alerts"],
        }
    return {
        "ok": True,
        "person_name": saved["name"],
        "speech": (
            f"Registered {saved['name']}. "
            "Say when they need to take medicine, for example "
            f"{saved['name']} needs to take medicine at 8 AM."
        ),
        "alerts": today_board(store)["alerts"],
    }


def add_medicine(store: Store, person_name: str, dose_label: str, times: str, days: str = "") -> dict[str, Any]:
    person = _tidy_name(person_name)
    label = " ".join(dose_label.split()) or "medicine"
    clocks = [part.strip() for part in times.split(",") if part.strip()]
    clocks = [clock for clock in clocks if valid_clock(clock)]
    chosen = parse_days(days)
    if not person:
        return {"ok": False, "speech": "Say who needs the medicine."}
    if not clocks:
        return {
            "ok": False,
            "speech": f"I heard {person}, but not a time. Say 8 AM, or morning and evening.",
        }
    if chosen is not None and not chosen:
        return {"ok": False, "speech": "I didn't understand the days. Say for example Monday and Friday, weekdays, or every day."}
    wanted = chosen if chosen is not None else list(range(7))
    known = store.find_person(person)
    display = known or person
    if not known:
        store.add_person(display)
    added: list[str] = []
    kept: list[str] = []
    widened: list[str] = []
    for clock in clocks:
        existing = _find_schedule(store, display, label, clock)
        if existing is None:
            store.add_schedule(display, label, clock, days=days_to_str(wanted))
            added.append(speak_time(clock))
            continue
        have = days_from_str(existing.get("days"))
        merged = sorted(set(have) | set(wanted))
        if merged == have:
            kept.append(speak_time(clock))
        else:
            store.update_schedule(int(existing["id"]), existing["dose_label"], clock, days_to_str(merged))
            widened.append(speak_time(clock))
    board = today_board(store)
    when = speak_days(wanted)
    parts: list[str] = []
    if added:
        parts.append(f"Added {display}'s {label} at {_join(added)}, {when}.")
    if widened:
        parts.append(f"Extended {display}'s {label} at {_join(widened)} to {when}.")
    if kept:
        parts.append(f"{display}'s {label} was already scheduled at {_join(kept)}, {when}.")
    return {
        "ok": True,
        "person_name": display,
        "dose_label": label,
        "added": added,
        "alerts": board["alerts"],
        "speech": " ".join(parts),
    }


def remove_medicine(
    store: Store,
    person_name: str = "",
    dose_label: str = "",
    time_hint: str = "",
) -> dict[str, Any]:
    person = person_name.strip()
    label = dose_label.strip()
    if not person and not label:
        return {"ok": False, "speech": "Say whose medicine to remove, and which one, for example remove dopamine from Raj."}
    rows = _filter_rows(store.list_schedules(), person, label, time_hint)
    if not rows:
        return {"ok": False, "speech": "I couldn't find that medicine on the schedule.", "alerts": today_board(store)["alerts"]}
    people = {row["person_name"] for row in rows}
    labels = {row["dose_label"].lower() for row in rows}
    if not label and not time_hint.strip():
        who = sorted(people)[0]
        names = _join(sorted({row["dose_label"] for row in rows}))
        return {"ok": False, "speech": f"{who} has {names}. Say which medicine to remove, or say remove person {who}."}
    if len(people) > 1:
        return {"ok": False, "speech": f"More than one person has that. Say whose to remove: {_join(sorted(people))}."}
    if not label and len(labels) > 1:
        names = _join(sorted({row["dose_label"] for row in rows}))
        who = next(iter(people))
        return {"ok": False, "speech": f"{who} has {names}. Say which medicine to remove."}
    for row in rows:
        store.delete_schedule(int(row["id"]))
    who = next(iter(people))
    name = rows[0]["dose_label"] if len(labels) == 1 else "medicines"
    times = _join([speak_time(row["time_local"]) for row in rows])
    return {
        "ok": True,
        "person_name": who,
        "removed": len(rows),
        "alerts": today_board(store)["alerts"],
        "speech": f"Removed {who}'s {name} at {times}.",
    }


def remove_person(store: Store, name: str) -> dict[str, Any]:
    known = store.find_person(name)
    if not known:
        return {"ok": False, "speech": f"I don't have anyone called {name.strip() or 'that'}."}
    store.delete_person(known)
    return {
        "ok": True,
        "person_name": known,
        "alerts": today_board(store)["alerts"],
        "speech": f"Removed {known} and all of their medicines.",
    }


def change_medicine(
    store: Store,
    person_name: str,
    dose_label: str,
    times: str = "",
    days: str = "",
) -> dict[str, Any]:
    clocks = [part.strip() for part in times.split(",") if part.strip()]
    if any(not valid_clock(clock) for clock in clocks):
        return {"ok": False, "speech": "I didn't understand the time."}
    chosen = parse_days(days)
    if chosen is not None and not chosen:
        return {"ok": False, "speech": "I didn't understand the days. Say for example Monday and Friday, weekdays, or every day."}
    if not clocks and chosen is None:
        return {"ok": False, "speech": "Say the new time or days, for example change Raj's dopamine to 9 AM."}
    rows = _filter_rows(store.list_schedules(), person_name, dose_label, "")
    if not rows:
        return {"ok": False, "speech": "I couldn't find that medicine on the schedule.", "alerts": today_board(store)["alerts"]}
    if len({row["person_name"] for row in rows}) > 1:
        return {"ok": False, "speech": "More than one person has that. Say whose medicine to change."}
    who = rows[0]["person_name"]
    label = rows[0]["dose_label"]
    new_days = days_to_str(chosen) if chosen is not None else None
    if clocks:
        for index, clock in enumerate(clocks):
            if index < len(rows):
                row = rows[index]
                store.update_schedule(int(row["id"]), row["dose_label"], clock, new_days or row["days"])
            else:
                store.add_schedule(who, label, clock, days=new_days or rows[0]["days"])
        for row in rows[len(clocks):]:
            store.delete_schedule(int(row["id"]))
    else:
        for row in rows:
            store.update_schedule(int(row["id"]), row["dose_label"], row["time_local"], new_days)
    when = ", ".join(
        part for part in (
            _join([speak_time(clock) for clock in clocks]) if clocks else "",
            speak_days(chosen) if chosen is not None else "",
        ) if part
    )
    change = f"to {when}" if clocks else f"to run {when}"
    return {
        "ok": True,
        "person_name": who,
        "alerts": today_board(store)["alerts"],
        "speech": f"Changed {who}'s {label} {change}.",
    }


def clear_today_log(store: Store, person_name: str = "", now: datetime | None = None) -> dict[str, Any]:
    moment = local_now(now)
    person = person_name.strip()
    if person and not store.find_person(person):
        return {"ok": False, "speech": f"I don't have anyone called {person}."}
    cleared = store.clear_logs(moment.date().isoformat(), person)
    who = store.find_person(person) if person else ""
    scope = f"{who}'s" if who else "today's"
    return {
        "ok": True,
        "cleared": cleared,
        "alerts": today_board(store, moment)["alerts"],
        "speech": f"Cleared {scope} log. {cleared} {'entry' if cleared == 1 else 'entries'} removed." if cleared
        else f"There was nothing logged in {scope} log.",
    }


def list_medicines(store: Store, person_name: str = "") -> dict[str, Any]:
    rows = _filter_rows(store.list_schedules(), person_name, "", "")
    who = person_name.strip().title()
    if not rows:
        if who and store.find_person(who):
            return {"ok": True, "schedules": [], "speech": f"{store.find_person(who)} has no medicines yet."}
        if who:
            return {"ok": False, "speech": f"I don't have anyone called {who}."}
        return {"ok": True, "schedules": [], "speech": "No medicines are scheduled yet."}
    by_person: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        by_person.setdefault(row["person_name"], {}).setdefault(row["dose_label"], []).append(row)
    sentences: list[str] = []
    for person, meds in sorted(by_person.items()):
        parts = []
        for label, items in sorted(meds.items()):
            groups: dict[str, list[str]] = {}
            for item in sorted(items, key=lambda r: r["time_local"]):
                groups.setdefault(speak_days(days_from_str(item.get("days"))), []).append(speak_time(item["time_local"]))
            parts.append("; ".join(f"{label} at {_join(times)}, {when}" for when, times in groups.items()))
        sentences.append(f"{person} takes {'; '.join(parts)}.")
    return {
        "ok": True,
        "schedules": [_describe(row) for row in rows],
        "alerts": today_board(store)["alerts"],
        "speech": " ".join(sentences),
    }


def _find_schedule(store: Store, person: str, label: str, clock: str) -> dict[str, Any] | None:
    for row in store.list_schedules():
        if (
            row["person_name"].lower() == person.lower()
            and row["dose_label"].lower() == label.lower()
            and row["time_local"] == clock
        ):
            return row
    return None


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _clean_schedule(person_name: str, dose_label: str, time_local: str, days: Any) -> tuple[str, str, str, str]:
    person = person_name.strip()
    label = dose_label.strip()
    clock = time_local.strip()
    if not person or not label:
        raise ValueError("Person and medicine are required.")
    if not valid_clock(clock):
        raise ValueError("Time must look like 08:00 or 20:00.")
    if days in (None, "", []):
        chosen = list(range(7))
    else:
        text = ",".join(str(d) for d in days) if isinstance(days, (list, tuple)) else str(days)
        chosen = parse_days(text)
        if not chosen:
            raise ValueError("Pick at least one day.")
    return person, label, clock, days_to_str(chosen)


def add_schedule(store: Store, person_name: str, dose_label: str, time_local: str, days: Any = None) -> dict[str, Any]:
    person, label, clock, day_text = _clean_schedule(person_name, dose_label, time_local, days)
    return store.add_schedule(person, label, clock, days=day_text)


def update_schedule(store: Store, schedule_id: int, dose_label: str, time_local: str, days: Any = None) -> bool:
    current = next((row for row in store.list_schedules() if int(row["id"]) == schedule_id), None)
    if current is None:
        return False
    _, label, clock, day_text = _clean_schedule(current["person_name"], dose_label, time_local, days)
    return store.update_schedule(schedule_id, label, clock, day_text)


def _present(store: Store, row: dict[str, Any], day: str, moment: datetime) -> dict[str, Any]:
    log = store.get_log(int(row["id"]), day)
    scheduled = scheduled_at(day, row["time_local"], moment.tzinfo)
    state = dose_state(scheduled, moment, log)
    return {
        "schedule_id": int(row["id"]),
        "person_name": row["person_name"],
        "dose_label": row["dose_label"],
        "time_local": row["time_local"],
        "time_spoken": speak_time(row["time_local"]),
        "state": state,
        "reason": (log or {}).get("reason", ""),
        "logged_at": (log or {}).get("logged_at"),
        "minutes_late": minutes_late(scheduled, moment) if state == "overdue" else 0,
    }


def _filter_person(doses: list[dict[str, Any]], person_name: str) -> list[dict[str, Any]]:
    needle = person_name.strip().lower()
    if not needle:
        return doses
    return [dose for dose in doses if needle in dose["person_name"].lower()]


def _filter_rows(
    rows: list[dict[str, Any]],
    person_name: str,
    dose_label: str,
    time_hint: str,
) -> list[dict[str, Any]]:
    chosen = rows
    if person_name.strip():
        needle = person_name.strip().lower()
        chosen = [row for row in chosen if needle in row["person_name"].lower()]
    if dose_label.strip():
        needle = dose_label.strip().lower()
        chosen = [row for row in chosen if needle in row["dose_label"].lower()]
    if time_hint.strip():
        chosen = [row for row in chosen if time_matches(row["time_local"], time_hint)]
    return chosen


def _choose_for_log(doses: list[dict[str, Any]], narrowed: str) -> dict[str, Any] | None:
    if len(doses) == 1:
        return doses[0]
    if narrowed:
        return None
    open_doses = [dose for dose in doses if dose["state"] in OPEN_STATES]
    if len(open_doses) == 1:
        return open_doses[0]
    return None


def _speak_due(
    due: list[dict[str, Any]],
    overdue: list[dict[str, Any]],
    nxt: dict[str, Any] | None,
) -> str:
    parts: list[str] = []
    for dose in overdue:
        parts.append(f"{_label(dose)} is overdue.")
    for dose in due:
        parts.append(f"{_label(dose)} is due now.")
    if not parts:
        if nxt:
            return f"Nothing is due right now. The next dose is {_label(nxt)}."
        return "Nothing is due. Today's doses are already logged."
    if nxt and not due:
        parts.append(f"The next dose is {_label(nxt)}.")
    return " ".join(parts)


def _speak_summary(dose: dict[str, Any]) -> str:
    """One plain sentence per dose, such as 'Raj took the 8 AM dopamine.'"""
    what = f"{dose['time_spoken']} {dose['dose_label']}"
    who = dose["person_name"]
    state = dose["state"]
    if state == "taken":
        return f"{who} took the {what}."
    if state == "skipped":
        note = f" ({dose['reason']})" if dose["reason"] else ""
        return f"{who} skipped the {what}{note}."
    if state == "overdue":
        return f"{who}'s {what} is overdue."
    if state == "due":
        return f"{who}'s {what} is due now."
    return f"{who}'s {what} is later today."


def _speak_log(dose: dict[str, Any]) -> str:
    if dose["state"] == "skipped":
        note = dose["reason"] or "no reason was given"
        return f"Logged a skip for {_label(dose)}. The note was: {note}."
    return f"Logged. {_who(dose)} took the {dose['time_spoken']} {dose['dose_label']}."


def _speak_status(dose: dict[str, Any]) -> str:
    label = _label(dose)
    if dose["state"] == "taken":
        return f"Yes. {label} was taken."
    if dose["state"] == "skipped":
        note = dose["reason"] or "no reason was given"
        return f"{label} was skipped. The note was: {note}."
    if dose["state"] == "overdue":
        return f"No. {label} is overdue."
    if dose["state"] == "due":
        return f"Not yet. {label} is due now."
    return f"Not yet. {label} is later today."


def _label(dose: dict[str, Any]) -> str:
    return f"{dose['person_name']}'s {dose['time_spoken']} {dose['dose_label']}"


def _who(dose: dict[str, Any]) -> str:
    return str(dose["person_name"])

