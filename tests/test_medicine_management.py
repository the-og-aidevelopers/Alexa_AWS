import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from dose_check import service
from dose_check.db import Store
from dose_check.intent import route_utterance
from dose_check.logic import parse_days, speak_days

TZ = ZoneInfo("America/New_York")
SATURDAY = datetime(2026, 10, 3, 8, 10, tzinfo=TZ)
MONDAY = datetime(2026, 10, 5, 8, 10, tzinfo=TZ)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "dose.sqlite")


def test_parse_and_speak_days():
    assert parse_days("monday and friday") == [0, 4]
    assert parse_days("weekdays") == [0, 1, 2, 3, 4]
    assert parse_days("friday to monday") == [0, 4, 5, 6]
    assert parse_days("") is None
    assert parse_days("blah") == []
    assert speak_days([5, 6]) == "on weekends"


def test_days_limit_which_doses_appear_today(store):
    service.add_medicine(store, "Raj", "dopamine", "08:00", "monday,friday")
    service.add_medicine(store, "Raj", "vitamin", "08:00")
    assert [d["dose_label"] for d in service.today_board(store, SATURDAY)["doses"]] == ["vitamin"]
    assert {d["dose_label"] for d in service.today_board(store, MONDAY)["doses"]} == {"dopamine", "vitamin"}
    off_day = service.log_dose(store, "taken", "Raj", "dopamine", now=SATURDAY)
    assert off_day["ok"] is False
    assert "no doses scheduled today" in service.dose_status(store, "Raj", "dopamine", now=SATURDAY)["speech"]
    assert service.log_dose(store, "taken", "Raj", "dopamine", now=MONDAY)["ok"]


def test_multiple_people_are_independent(store):
    service.add_medicine(store, "Raj", "dopamine", "08:00")
    service.add_medicine(store, "Mom", "lisinopril", "08:00,20:00", "weekdays")
    service.log_dose(store, "taken", "Raj", now=MONDAY)
    states = {(d["person_name"], d["time_local"]): d["state"] for d in service.today_board(store, MONDAY)["doses"]}
    assert states[("Raj", "08:00")] == "taken"
    assert states[("Mom", "08:00")] != "taken"


def test_adding_again_widens_days(store):
    service.add_medicine(store, "Raj", "dopamine", "08:00", "monday")
    said = service.add_medicine(store, "Raj", "dopamine", "08:00", "friday")["speech"]
    assert "Extended" in said
    assert len(store.list_schedules()) == 1
    assert store.list_schedules()[0]["days"] == "0,4"


def test_remove_medicine_person_and_ambiguity(store):
    service.add_medicine(store, "Raj", "dopamine", "08:00,20:00")
    service.add_medicine(store, "Raj", "vitamin", "09:00")
    assert "Say which medicine" in service.remove_medicine(store, "Raj")["speech"]
    one = service.remove_medicine(store, "Raj", "dopamine", "08:00")
    assert one["ok"] and len(store.list_schedules()) == 2
    service.log_dose(store, "taken", "Raj", "vitamin", now=SATURDAY)
    assert service.remove_medicine(store, "Raj", "dopamine")["ok"]
    assert [r["dose_label"] for r in store.list_schedules()] == ["vitamin"]
    assert not service.remove_medicine(store, "Raj", "aspirin")["ok"]
    assert service.remove_person(store, "raj")["ok"]
    assert store.list_people() == [] and store.list_schedules() == []
    with sqlite3.connect(store.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM dose_logs").fetchone()[0] == 0
    assert not service.remove_person(store, "Raj")["ok"]


def test_change_medicine_times_and_days(store):
    service.add_medicine(store, "Raj", "dopamine", "08:00,20:00")
    done = service.change_medicine(store, "Raj", "dopamine", "09:00", "weekends")
    assert done["ok"]
    rows = store.list_schedules()
    assert [(r["time_local"], r["days"]) for r in rows] == [("09:00", "5,6")]
    assert not service.change_medicine(store, "Raj", "dopamine")["ok"]


def test_list_medicines_speaks_times_and_days(store):
    service.add_medicine(store, "Raj", "dopamine", "08:00", "monday and friday")
    speech = service.list_medicines(store, "Raj")["speech"]
    assert speech == "Raj takes dopamine at 8 AM, on Monday and Friday."
    assert not service.list_medicines(store, "Nobody")["ok"]


def test_old_database_gets_days_column(tmp_path):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE schedules (id INTEGER PRIMARY KEY AUTOINCREMENT, household_id INTEGER NOT NULL DEFAULT 1,"
            " person_name TEXT NOT NULL, dose_label TEXT NOT NULL, time_local TEXT NOT NULL, created_at TEXT NOT NULL);"
            "INSERT INTO schedules (person_name, dose_label, time_local, created_at) VALUES ('Mom','x','08:00','now');"
        )
    assert Store(path).list_schedules()[0]["days"] == "0,1,2,3,4,5,6"


ROWS = [
    {"person_name": "Raj", "dose_label": "dopamine", "time_local": "08:00"},
    {"person_name": "Mom", "dose_label": "lisinopril", "time_local": "20:00"},
]


@pytest.mark.parametrize(
    "heard, tool, expected",
    [
        ("Raj needs to take dopamine at 8 am on monday and friday", "add_medicine", {"person_name": "Raj", "times": "08:00", "days": "on monday and friday"}),
        ("Mom takes aspirin every day at 9 am", "add_medicine", {"dose_label": "aspirin", "times": "09:00"}),
        ("remove dopamine from Raj", "remove_medicine", {"person_name": "Raj", "dose_label": "dopamine"}),
        ("delete person Raj", "remove_person", {"name": "Raj"}),
        ("change Raj's dopamine to 9 am", "change_medicine", {"person_name": "Raj", "times": "09:00"}),
        ("what medicines does Raj take", "list_medicines", {"person_name": "Raj"}),
        ("what medicine is due now", "list_due_doses", {}),
    ],
)
def test_speech_routes_management_commands(heard, tool, expected):
    routed = route_utterance(heard, ROWS)
    assert routed["tool"] == tool
    for key, value in expected.items():
        assert routed["arguments"][key] == value


def test_clear_today_log_by_chat(store):
    service.add_medicine(store, "Raj", "dopamine", "08:00")
    service.add_medicine(store, "Mom", "aspirin", "08:00")
    service.log_dose(store, "taken", "Raj", now=SATURDAY)
    service.log_dose(store, "taken", "Mom", now=SATURDAY)
    assert route_utterance("clear today's log", ROWS)["tool"] == "clear_today_log"
    assert route_utterance("reset Raj's log for today", ROWS, ["Raj"])["arguments"] == {"person_name": "Raj"}
    assert service.clear_today_log(store, "Raj", SATURDAY)["cleared"] == 1
    states = {d["person_name"]: d["state"] for d in service.today_board(store, SATURDAY)["doses"]}
    assert states["Mom"] == "taken" and states["Raj"] != "taken"
    assert service.clear_today_log(store, "", SATURDAY)["cleared"] == 1
    assert not service.clear_today_log(store, "Nobody", SATURDAY)["ok"]
