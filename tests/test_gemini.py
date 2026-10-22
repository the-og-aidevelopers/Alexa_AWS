import types as pytypes

import pytest

from dose_check import agent, gemini, transcribe


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY", "DOSE_TRANSCRIBE_PROVIDER", "GEMINI_ROUTING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(gemini, "_client", None)
    gemini.reset()
    yield
    gemini.reset()


class FakeModels:
    def __init__(self, calls, error=None):
        self.calls, self.error, self.seen = calls, error, {}

    def generate_content(self, model, contents, config):
        self.seen = {"model": model, "contents": contents, "config": config}
        if self.error:
            raise self.error
        return pytypes.SimpleNamespace(function_calls=self.calls)


def fake_client(calls=None, error=None, text="Add Rahul", seen=None):
    models = FakeModels(calls, error)

    class Interactions:
        def create(self, **kwargs):
            if seen is not None:
                seen.update(kwargs)
            return pytypes.SimpleNamespace(output_text=f" {text} ")

    return pytypes.SimpleNamespace(models=models, interactions=Interactions())


def call(name, **args):
    return pytypes.SimpleNamespace(name=name, args=args)


def test_every_tool_converts_to_a_valid_gemini_declaration():
    from google.genai import types

    for spec in agent._TOOL_SPECS:
        types.FunctionDeclaration(
            name=spec["toolSpec"]["name"],
            description=spec["toolSpec"]["description"],
            parameters_json_schema=spec["toolSpec"]["inputSchema"]["json"],
        )


def test_gemini_maps_a_sentence_to_the_closest_tool(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    client = fake_client([call("add_medicine", person_name="Mom", dose_label="medicine", times="08:00")])
    monkeypatch.setattr(gemini, "_client", client)
    choice = agent.decide("add mom medicine at 8AM", "older_adult", [], ["Mom"])
    assert choice["tool"] == "add_medicine"
    assert choice["arguments"] == {"person_name": "Mom", "dose_label": "medicine", "times": "08:00"}
    assert choice["router"] == "gemini"
    assert "Known people: Mom" in client.models.seen["config"].system_instruction


def test_gemini_picks_a_tool_without_arguments(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(gemini, "_client", fake_client([call("list_due_doses")]))
    choice = agent.decide("what's due now", "older_adult", [], [])
    assert (choice["tool"], choice["arguments"]) == ("list_due_doses", {"person_name": ""})


def test_bad_gemini_output_falls_back_to_the_rules(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    for client in (
        fake_client(error=RuntimeError("quota")),
        fake_client([call("delete_everything")]),
        fake_client([call("log_dose", status="maybe")]),
        fake_client([]),
    ):
        monkeypatch.setattr(gemini, "_client", client)
        choice = agent.decide("What's due now?", "older_adult", [], [])
        assert choice["tool"] == "list_due_doses"
        assert choice["router"] == "rules"


def test_routing_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("GEMINI_ROUTING", "0")
    monkeypatch.setattr(gemini, "_client", fake_client(error=AssertionError("must not be called")))
    assert agent.decide("What's due now?", "older_adult", [], [])["router"] == "rules"


def test_transcription_sends_vocabulary_and_prefers_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "other")
    seen = {}
    monkeypatch.setattr(gemini, "_client", fake_client(seen=seen))
    assert transcribe.chain()[:2] == ["gemini", "elevenlabs"]
    assert transcribe.transcribe(b"audio", "", ["Rahul", "Mom"]) == "Add Rahul"
    assert seen["model"] == "gemini-3.5-transcribe"
    assert seen["generation_config"]["transcription_config"]["custom_vocabulary"] == ["Rahul", "Mom"]
    assert seen["input"][0]["type"] == "audio"


def test_transcription_falls_through_when_gemini_fails(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    class Broken:
        class interactions:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("429")

    class Model:
        def transcribe(self, *args, **kwargs):
            class Segment:
                text = "from local"
            return [Segment()], None

    monkeypatch.setattr(gemini, "_client", Broken())
    monkeypatch.setattr(transcribe, "_load", lambda: Model())
    monkeypatch.setattr(transcribe, "_local_installed", lambda: True)
    assert transcribe.transcribe(b"audio", "") == "from local"


def test_local_can_be_forced_even_with_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("DOSE_TRANSCRIBE_PROVIDER", "local")
    monkeypatch.setattr(transcribe, "_local_installed", lambda: True)
    assert transcribe.chain() == ["local"]


def test_quota_errors_pause_gemini_so_phrases_are_not_delayed(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(gemini, "_client", fake_client(error=RuntimeError("402 Your prepayment credits are depleted")))
    assert gemini.enabled() and transcribe.chain()[0] == "gemini"
    assert agent.decide("What's due now?", "older_adult", [], [])["router"] == "rules"
    assert not gemini.enabled()
    assert "gemini" not in transcribe.chain() and not gemini.routing_enabled()
    gemini.reset()
    assert gemini.enabled()


def test_other_errors_do_not_pause_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(gemini, "_client", fake_client(error=RuntimeError("network down")))
    agent.decide("What's due now?", "older_adult", [], [])
    assert gemini.enabled()
