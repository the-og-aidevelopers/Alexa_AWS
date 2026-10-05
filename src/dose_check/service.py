"""Dose tools. Answers come from the schedule and the log, not from a model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from dose_check.db import Store
from dose_check.logic import (
    dose_state,
    local_now,
    minutes_late,
    scheduled_at,
    speak_time,
    time_matches,
    valid_clock,
)

OPEN_STATES = {"due", "overdue"}


def today_board(store: Store, now: datetime | None = None) -> dict[str, Any]:
    moment = local_now(now)
    day = moment.date().isoformat()
    doses = [_present(store, row, day, moment) for row in store.list_schedules()]
    alerts = [dose for dose in doses if dose["state"] == "overdue"]
    return {
        "day": day,
        "now": moment.isoformat(timespec="seconds"),
        "doses": doses,
        "alerts": alerts,
        "people": store.list_people(),
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
    matches = _filter_rows(store.list_schedules(), person_name, dose_label, time_hint)
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
    rows = _filter_rows(store.list_schedules(), person_name, dose_label, time_hint)
    if not rows:
        board = today_board(store, moment)
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
    names = {dose["person_name"] for dose in doses}
    who = person_name.strip() or (next(iter(names)) if len(names) == 1 else "the household")
    speech = (
        f"Today for {who}: {counts['taken']} taken, {counts['skipped']} skipped, "
        f"{counts['overdue']} overdue, {counts['due']} due now, "
        f"and {counts['upcoming']} later, out of {len(doses)} doses."
    )
    return {"ok": True, "counts": counts, "doses": doses, "alerts": board["alerts"], "speech": speech}


def register_person(store: Store, name: str) -> dict[str, Any]:
    cleaned = " ".join(name.split())
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


def add_medicine(store: Store, person_name: str, dose_label: str, times: str) -> dict[str, Any]:
    person = " ".join(person_name.split())
    label = " ".join(dose_label.split()) or "medicine"
    clocks = [part.strip() for part in times.split(",") if part.strip()]
    clocks = [clock for clock in clocks if valid_clock(clock)]
    if not person:
        return {"ok": False, "speech": "Say who needs the medicine."}
    if not clocks:
        return {
            "ok": False,
            "speech": f"I heard {person}, but not a time. Say 8 AM, or morning and evening.",
        }
    known = store.find_person(person)
    display = known or person
    if not known:
        store.add_person(display)
    added: list[str] = []
    kept: list[str] = []
    for clock in clocks:
        if _already_scheduled(store, display, label, clock):
            kept.append(speak_time(clock))
            continue
        store.add_schedule(display, label, clock)
        added.append(speak_time(clock))
    board = today_board(store)
    if added and kept:
        speech = f"Added {display}'s {label} at { _join(added) }. Already scheduled at { _join(kept) }."
    elif added:
        speech = f"Added {display}'s {label} at { _join(added) }."
    else:
        speech = f"{display}'s {label} is already scheduled at { _join(kept) }."
    return {
        "ok": True,
        "person_name": display,
        "dose_label": label,
        "added": added,
        "alerts": board["alerts"],
        "speech": speech,
    }


def _already_scheduled(store: Store, person: str, label: str, clock: str) -> bool:
    for row in store.list_schedules():
        if (
            row["person_name"].lower() == person.lower()
            and row["dose_label"].lower() == label.lower()
            and row["time_local"] == clock
        ):
            return True
    return False


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def add_schedule(store: Store, person_name: str, dose_label: str, time_local: str) -> dict[str, Any]:
    person = person_name.strip()
    label = dose_label.strip()
    clock = time_local.strip()
    if not person or not label:
        raise ValueError("Person and medicine are required.")
    if not valid_clock(clock):
        raise ValueError("Time must look like 08:00 or 20:00.")
    return store.add_schedule(person, label, clock)


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

