import httpx
import pytest

from dose_check import transcribe


def test_prompt_contains_household_vocabulary():
    prompt = transcribe.build_prompt(["Raj", "Mom"], ["zolpidem"])
    assert "Raj, Mom" in prompt and "zolpidem" in prompt and "dopamine" in prompt


def test_echo_of_prompt_is_discarded(monkeypatch):
    class Model:
        def transcribe(self, *args, **kwargs):
            class Segment:
                text = " Raj, Mom "
            return [Segment()], None

    monkeypatch.setattr(transcribe, "_load", lambda: Model())
    assert transcribe.transcribe(b"x", transcribe.build_prompt(["Raj", "Mom"], [])) == ""
    assert transcribe.transcribe(b"x", "") == "Raj, Mom"


def test_endpoint_passes_household_vocabulary(monkeypatch, tmp_path):
    monkeypatch.setenv("DOSE_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("DOSE_AUTH_PROVIDER", "demo")
    from dose_check import server
    from dose_check.db import Store

    store = Store(tmp_path / "iso.sqlite")
    store.add_schedule("Raj", "dopamine", "08:00")
    monkeypatch.setattr(server, "store", store)
    seen = {}

    def fake(audio, prompt):
        seen.update(audio=audio, prompt=prompt)
        return "Raj took his dopamine"

    monkeypatch.setattr(server.stt, "available", lambda: True)
    monkeypatch.setattr(server.stt, "transcribe", fake)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test", trust_env=False) as client:
            ok = await client.post("/api/transcribe", content=b"audio", headers={"Content-Type": "audio/webm"})
            empty = await client.post("/api/transcribe", content=b"")
            return ok, empty

    import asyncio

    ok, empty = asyncio.run(run())
    assert ok.json() == {"text": "Raj took his dopamine"}
    assert seen["audio"] == b"audio" and "Raj" in seen["prompt"] and "dopamine" in seen["prompt"]
    assert empty.status_code == 400


def test_endpoint_reports_missing_engine(monkeypatch, tmp_path):
    monkeypatch.setenv("DOSE_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("DOSE_AUTH_PROVIDER", "demo")
    from dose_check import server

    monkeypatch.setattr(server.stt, "available", lambda: False)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test", trust_env=False) as client:
            return await client.post("/api/transcribe", content=b"audio")

    import asyncio

    assert asyncio.run(run()).status_code == 503


@pytest.mark.parametrize("said", ["I took the morning one.", "What's due now?"])
def test_sentences_from_the_prompt_are_not_mistaken_for_an_echo(monkeypatch, said):
    class Model:
        def transcribe(self, *args, **kwargs):
            class Segment:
                text = said
            return [Segment()], None

    monkeypatch.setattr(transcribe, "_load", lambda: Model())
    assert transcribe.transcribe(b"x", transcribe.build_prompt(["Raj"], [])) == said
