from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from dose_check.db import Store
from dose_check.agent import decide
from dose_check.intent import route_utterance
from dose_check.logic import dose_state, scheduled_at
from dose_check import service
from dose_check.speech import maybe_rephrase

TZ = ZoneInfo("America/New_York")
MORNING = datetime(2026, 10, 3, 10, 0, tzinfo=TZ)


@pytest.fixture
def store(tmp_path):
    saved = Store(tmp_path / "dose.sqlite")
    saved.add_schedule("Mom", "lisinopril", "08:00")
    saved.add_schedule("Mom", "lisinopril", "20:00")
    return saved


def test_grace_window_boundaries():
    scheduled = scheduled_at("2026-10-03", "08:00", TZ)
    assert dose_state(scheduled, datetime(2026, 10, 3, 8, 10, tzinfo=TZ), None) == "due"
    assert dose_state(scheduled, datetime(2026, 10, 3, 8, 30, tzinfo=TZ), None) == "due"
    assert dose_state(scheduled, datetime(2026, 10, 3, 8, 31, tzinfo=TZ), None) == "overdue"
    assert dose_state(scheduled, datetime(2026, 10, 3, 6, 0, tzinfo=TZ), None) == "upcoming"
    assert dose_state(scheduled, MORNING, {"status": "taken"}) == "taken"


def test_midmorning_board_marks_morning_overdue(store):
    board = service.today_board(store, MORNING)
    states = {dose["time_local"]: dose["state"] for dose in board["doses"]}
    assert states == {"08:00": "overdue", "20:00": "upcoming"}
    assert len(board["alerts"]) == 1
    assert board["alerts"][0]["minutes_late"] == 90


def test_log_taken_clears_the_alert(store):
    result = service.log_dose(store, "taken", time_hint="morning", now=MORNING)
    assert result["ok"] is True
    assert result["alerts"] == []
    assert "Logged" in result["speech"]


def test_skip_keeps_the_reason(store):
    result = service.log_dose(
        store,
        "skipped",
        time_hint="evening",
        reason="I feel dizzy",
        now=MORNING,
    )
    assert result["ok"] is True
    assert result["dose"]["state"] == "skipped"
    assert result["dose"]["reason"] == "I feel dizzy"
    assert "I feel dizzy" in result["speech"]


def test_ambiguous_log_does_not_write(store):
    result = service.log_dose(store, "taken", dose_label="lisinopril", now=MORNING)
    assert result["ok"] is False
    assert "more than one" in result["speech"]
    assert service.today_board(store, MORNING)["doses"][0]["state"] == "overdue"


def test_status_and_summary(store):
    service.log_dose(store, "taken", time_hint="morning", now=MORNING)
    status = service.dose_status(store, person_name="Mom", time_hint="evening", now=MORNING)
    assert "later today" in status["speech"]
    summary = service.summarize_day(store, "Mom", MORNING)
    assert summary["speech"].startswith("Today for Mom:")
    assert summary["counts"] == {
        "taken": 1,
        "skipped": 0,
        "due": 0,
        "overdue": 0,
        "upcoming": 1,
    }


def test_routes_the_demo_sentences():
    catalog = [
        {"person_name": "Mom", "dose_label": "lisinopril", "time_local": "08:00"},
        {"person_name": "Mom", "dose_label": "lisinopril", "time_local": "20:00"},
    ]
    due = route_utterance("What's due now?", catalog)
    assert due["tool"] == "list_due_doses"
    taken = route_utterance("I took the morning one", catalog)
    assert taken["tool"] == "log_dose"
    assert taken["arguments"]["status"] == "taken"
    assert taken["arguments"]["time_hint"] == "morning"
    skipped = route_utterance("I skipped the evening one, I feel dizzy", catalog)
    assert skipped["arguments"]["status"] == "skipped"
    assert skipped["arguments"]["time_hint"] == "evening"
    assert skipped["arguments"]["reason"] == "I feel dizzy"
    asked = route_utterance("Did Mom take her evening medicine?", catalog)
    assert asked["tool"] == "dose_status"
    assert asked["arguments"]["person_name"] == "Mom"
    assert asked["arguments"]["time_hint"] == "evening"
    assert route_utterance("How did today go?", catalog)["tool"] == "summarize_day"
    assert route_utterance("what's do you know", catalog)["tool"] == "list_due_doses"
    assert route_utterance("what do you know", catalog)["tool"] == "list_due_doses"
    assert route_utterance("what you know", catalog)["tool"] == "list_due_doses"
    heard_taken = route_utterance("I took the mourning one", catalog)
    assert heard_taken["tool"] == "log_dose"
    assert heard_taken["arguments"]["time_hint"] == "morning"
    heard_mom = route_utterance("did mum take her morning medicine", catalog)
    assert heard_mom["tool"] == "dose_status"
    assert heard_mom["arguments"]["time_hint"] == "morning"
    assert route_utterance("how did to day go", catalog)["tool"] == "summarize_day"


def test_voice_registers_a_person_and_a_medicine(tmp_path):
    saved = Store(tmp_path / "people.sqlite")
    registered = route_utterance("add this person, register him as Raj", [])
    assert registered["tool"] == "register_person"
    assert registered["arguments"]["name"] == "Raj"
    spoken = service.register_person(saved, registered["arguments"]["name"])
    assert "Registered Raj" in spoken["speech"]
    assert saved.list_people() == ["Raj"]

    medicine = route_utterance("Raj needs to take medicine at 8 AM and 8 PM", [])
    assert medicine["tool"] == "add_medicine"
    assert medicine["arguments"]["person_name"] == "Raj"
    assert medicine["arguments"]["dose_label"] == "medicine"
    assert medicine["arguments"]["times"] == "08:00,20:00"
    added = service.add_medicine(saved, **medicine["arguments"])
    assert "8 AM and 8 PM" in added["speech"]
    assert len(saved.list_schedules()) == 2

    slots = route_utterance("Priya needs to take lisinopril in the morning and the evening", [])
    assert slots["arguments"]["times"] == "08:00,20:00"
    assert slots["arguments"]["dose_label"] == "lisinopril"


def test_add_person_and_medicine_at_a_clock_time():
    spoken = route_utterance("ads Raj dopamine at 8:00 a.m.", [])
    assert spoken["tool"] == "add_medicine"
    assert spoken["arguments"]["person_name"] == "Raj"
    assert spoken["arguments"]["dose_label"] == "dopamine"
    heard_add = route_utterance("add raj dopamine at 8 am", [])
    assert heard_add["arguments"]["times"] == "08:00"
    assert spoken["tool"] == "add_medicine"
    assert spoken["arguments"] == {
        "person_name": "Raj",
        "dose_label": "dopamine",
        "times": "08:00",
    }
    heard = route_utterance("at Raj dopamine at 8:00 a.m.", [])
    assert heard["arguments"]["person_name"] == "Raj"
    assert heard["arguments"]["dose_label"] == "dopamine"
    assert heard["arguments"]["times"] == "08:00"
    swapped = route_utterance("address Docomo at 8:00 a.m.", [])
    assert swapped is None or swapped["arguments"]["dose_label"] == "dopamine"


def test_medicine_phrases_the_microphone_actually_hears():
    dopamine = route_utterance("Rajniti to take medicine at 8:00 a.m. dopamine", [])
    assert dopamine["tool"] == "add_medicine"
    assert dopamine["arguments"]["person_name"] == "Raj"
    assert dopamine["arguments"]["dose_label"] == "dopamine"
    assert dopamine["arguments"]["times"] == "08:00"
    heard = route_utterance("Raj takes to come in at 8:00 a.m.", [])
    assert heard["arguments"]["person_name"] == "Raj"
    assert heard["arguments"]["times"] == "08:00"
    bare = route_utterance("Raj needs to take medicine at 8", [])
    assert bare["arguments"]["times"] == "08:00"
    short = route_utterance("Raj take medicine at 8:00 a.m.", [])
    assert short["arguments"] == {
        "person_name": "Raj",
        "dose_label": "medicine",
        "times": "08:00",
    }


def test_register_works_without_the_word_as():
    assert route_utterance("register Raj", [])["arguments"]["name"] == "Raj"
    assert route_utterance("Mr Raj register", [])["arguments"]["name"] == "Raj"
    assert route_utterance("register MS Raj", [])["arguments"]["name"] == "Raj"


def test_voice_can_switch_mode_and_ask():
    catalog = [
        {"person_name": "Mom", "dose_label": "lisinopril", "time_local": "08:00"},
        {"person_name": "Mom", "dose_label": "lisinopril", "time_local": "20:00"},
    ]
    switched = decide("Switch to caregiver mode", "older_adult", catalog, use_bedrock=False)
    assert switched["speaker"] == "caregiver"
    assert switched["tool"] is None
    assert switched["speaker_changed"] is True

    both = decide(
        "Switch to caregiver mode and did Mom take her morning medicine?",
        "older_adult",
        catalog,
        use_bedrock=False,
    )
    assert both["speaker"] == "caregiver"
    assert both["tool"] == "dose_status"
    assert both["arguments"]["time_hint"] == "morning"

    back = decide("Switch to older adult mode", "caregiver", catalog, use_bedrock=False)
    assert back["speaker"] == "older_adult"
    assert back["tool"] is None


def test_bedrock_stays_off_without_the_flag(monkeypatch):
    monkeypatch.delenv("SPEAK_WITH_BEDROCK", raising=False)
    speech, used = maybe_rephrase({"ok": True}, "Logged.")
    assert speech == "Logged."
    assert used is False



def test_multi_person_log_requires_name_even_for_a_unique_medicine(store):
    store.add_person('Dad')
    result = service.log_dose(store,'taken',dose_label='lisinopril',time_hint='morning',now=MORNING)
    assert not result['ok']
    assert 'whose dose' in result['speech']
    assert store.get_log(store.list_schedules()[0]['id'], MORNING.date().isoformat()) is None
    assert service.log_dose(store,'taken',person_name='Mom',time_hint='morning',now=MORNING)['ok']


def test_dopamine_mishearings_are_repaired():
    from dose_check.intent import route_utterance

    expected = {"tool": "add_medicine", "arguments": {"person_name": "Raj", "dose_label": "dopamine", "times": "08:00"}}
    for heard in (
        "Raj needs to take medicine lo for me at 8:00 a.m.",
        "Raaz rebooting a medicine at 8:00 a.m.",
        "raj needs to take his dopamine at 8am",
    ):
        assert route_utterance(heard, []) == expected


def test_third_person_taken_and_status():
    from dose_check.intent import route_utterance

    rows = [{"person_name": "Raj", "dose_label": "dopamine", "time_local": "08:00"}]
    taken = route_utterance("Raj took his medicine at 8:00 a.m.", rows)
    assert taken["tool"] == "log_dose"
    assert taken["arguments"]["status"] == "taken"
    assert taken["arguments"]["person_name"] == "Raj"
    assert taken["arguments"]["time_hint"] == "08:00"
    assert route_utterance("Raj has taken his dopamine", rows)["arguments"]["status"] == "taken"
    for heard in ("What is Raj's status", "How is Raj doing", "Raj's current medicine status"):
        routed = route_utterance(heard, rows)
        assert routed["tool"] == "dose_status"
        assert routed["arguments"]["person_name"] == "Raj"
