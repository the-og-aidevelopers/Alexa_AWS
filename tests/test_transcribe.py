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

    def fake(audio, prompt, keyterms=None):
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


def _scribe_client(monkeypatch, handler):
    import httpx

    real = httpx.post
    transport = httpx.MockTransport(handler)

    def post(url, **kwargs):
        with httpx.Client(transport=transport) as client:
            return client.post(url, **kwargs)

    monkeypatch.setattr(httpx, "post", post)
    return real


def test_scribe_v2_is_used_when_a_key_is_set(monkeypatch):
    import httpx

    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers["xi-api-key"]
        seen["body"] = request.content
        return httpx.Response(200, json={"text": " Add Rahul. "})

    _scribe_client(monkeypatch, handler)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "secret")
    monkeypatch.delenv("DOSE_TRANSCRIBE_PROVIDER", raising=False)
    monkeypatch.setattr(transcribe, "_load", lambda: pytest.fail("local model must not run"))
    assert transcribe.provider() == "elevenlabs"
    assert transcribe.transcribe(b"audio", "prompt", ["Raj"]) == "Add Rahul."
    assert seen["url"] == "https://api.elevenlabs.io/v1/speech-to-text"
    assert seen["key"] == "secret"
    assert b"scribe_v2" in seen["body"] and b"keyterms" not in seen["body"]


def test_keyterms_are_sent_only_when_enabled(monkeypatch):
    import httpx

    seen = {}

    def handler(request):
        seen["body"] = request.content
        return httpx.Response(200, json={"text": "ok"})

    _scribe_client(monkeypatch, handler)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "secret")
    monkeypatch.setenv("ELEVENLABS_KEYTERMS", "1")
    transcribe.transcribe(b"audio", "", transcribe.build_keyterms(["Rahul"], []))
    assert seen["body"].count(b'name="keyterms"') >= 2 and b"Rahul" in seen["body"]


def test_out_of_credit_scribe_falls_back_to_local(monkeypatch):
    import httpx

    _scribe_client(monkeypatch, lambda request: httpx.Response(401, json={"detail": "quota_exceeded"}))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "secret")

    class Model:
        def transcribe(self, *args, **kwargs):
            class Segment:
                text = "from local"
            return [Segment()], None

    monkeypatch.setattr(transcribe, "_load", lambda: Model())
    monkeypatch.setattr(transcribe, "_local_installed", lambda: True)
    assert transcribe.transcribe(b"audio", "") == "from local"


def test_local_provider_can_be_forced(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "secret")
    monkeypatch.setenv("DOSE_TRANSCRIBE_PROVIDER", "local")
    assert transcribe.provider() == "local"
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    monkeypatch.delenv("DOSE_TRANSCRIBE_PROVIDER")
    assert transcribe.provider() == "local"
