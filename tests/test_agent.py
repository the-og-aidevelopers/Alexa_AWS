from types import SimpleNamespace

import pytest

from dose_check.agent import DOSE_TOOLS, decide


@pytest.fixture
def bedrock(monkeypatch):
    monkeypatch.setenv("AWS_ENABLED", "1")
    import boto3

    captured = {}

    def install(blocks=None, error=None):
        def converse(**kwargs):
            captured["request"] = kwargs
            if error:
                raise error
            return {"output": {"message": {"content": blocks}}}

        def client(service, **kwargs):
            captured["service"] = service
            captured["config"] = kwargs["config"]
            return SimpleNamespace(converse=converse)

        monkeypatch.setattr(boto3, "client", client)
        return captured

    return install


def tool(name, arguments):
    return {"toolUse": {"name": name, "input": arguments}}


@pytest.mark.parametrize("name,args", [
    ("list_due_doses", {"person_name": "Mom"}),
    ("log_dose", {"status": "skipped", "time_hint": "evening", "reason": "I feel dizzy"}),
    ("dose_status", {"person_name": "Mom", "time_hint": "morning"}),
    ("summarize_day", {}),
    ("register_person", {"name": "Raj"}),
    ("add_medicine", {"person_name": "Raj", "times": "08:00,20:00"}),
])
def test_model_routes_all_six_tools(bedrock, name, args):
    captured = bedrock([tool(name, args)])
    choice = decide("A paraphrased request", "older_adult", [], use_bedrock=True)
    assert choice["tool"] == name
    assert choice["used_bedrock"] is True
    assert all(choice["arguments"][key] == value for key, value in args.items())
    assert [item["toolSpec"]["name"] for item in captured["request"]["toolConfig"]["tools"]] == list(DOSE_TOOLS)
    assert captured["config"].read_timeout == 10
    assert captured["config"].retries["total_max_attempts"] == 1


@pytest.mark.parametrize("blocks", [
    [tool("log_dose", {"status": "unknown"})],
    [tool("log_dose", {})],
    [tool("log_dose", {"status": None})],
    [tool("log_dose", {"status": True})],
    [tool("log_dose", {"status": "taken", "person_name": ["Mom"]})],
    [tool("log_dose", {"status": "taken", "unexpected": "ignored"})],
    [tool("log_dose", "taken")],
    [tool("log_dose", None)],
    [tool("delete_all_logs", {})],
    [tool("log_dose", {"status": "taken"}), tool("register_person", {"name": "Raj"})],
    [tool("register_person", {})],
    [tool("add_medicine", {"person_name": "Raj"})],
])
def test_invalid_model_call_does_not_become_a_taken_dose(bedrock, blocks):
    bedrock(blocks)
    choice = decide("Unrecognized sentence", "older_adult", [], use_bedrock=True)
    assert choice["tool"] is None
    assert choice["used_bedrock"] is False


def test_rejected_model_status_falls_back_to_the_actual_skipped_statement(bedrock):
    bedrock([tool("log_dose", {"status": "unknown"})])
    choice = decide("I skipped the evening one, I feel dizzy", "older_adult", [], use_bedrock=True)
    assert choice["arguments"]["status"] == "skipped"
    assert choice["arguments"]["reason"] == "I feel dizzy"
    assert choice["used_bedrock"] is False


def test_provider_failure_preserves_local_routing(bedrock):
    bedrock(error=TimeoutError("Bedrock timed out"))
    choice = decide("What's due now?", "older_adult", [], use_bedrock=True)
    assert choice["tool"] == "list_due_doses"
    assert choice["used_bedrock"] is False


def test_local_routing_preserves_skip_reason_and_mode_contractions():
    choice = decide(
        "I'm the caregiver and I skipped the evening one because I don't feel well",
        "older_adult", [], use_bedrock=False,
    )
    assert choice["speaker"] == "caregiver"
    assert choice["arguments"]["reason"] == "I don't feel well"


def test_mode_only_sentence_makes_no_model_call(bedrock):
    captured = bedrock([tool("log_dose", {"status": "taken"})])
    choice = decide("Switch to caregiver mode", "older_adult", [], use_bedrock=True)
    assert choice["speaker"] == "caregiver"
    assert choice["tool"] is None
    assert "request" not in captured
