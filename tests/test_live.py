import asyncio
import types as pytypes

import pytest
from starlette.testclient import TestClient

from dose_check import live


class FakeSession:
    """Plays back Gemini's messages once the browser has sent audio and its end marker."""

    def __init__(self, script):
        self.script, self.audio, self.ended = script, [], asyncio.Event()

    async def send_realtime_input(self, audio=None, audio_stream_end=None):
        if audio is not None:
            self.audio.append((audio.data, audio.mime_type))
        if audio_stream_end:
            self.ended.set()

    async def receive(self):
        for kind, text in self.script:
            await asyncio.sleep(0.01)
            note = pytypes.SimpleNamespace(text=text)
            yield pytypes.SimpleNamespace(
                server_content=pytypes.SimpleNamespace(
                    interim_input_transcription=note if kind == "partial" else None,
                    input_transcription=note if kind == "final" else None,
                )
            )
        await asyncio.sleep(3600)


def connector(session, seen=None):
    class Context:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    def connect(vocabulary):
        if seen is not None:
            seen.append(vocabulary)
        return Context()

    return connect


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("DOSE_DB", str(tmp_path / "live.sqlite"))
    monkeypatch.setenv("DOSE_AUTH_PROVIDER", "demo")
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    from dose_check import server
    from dose_check.db import Store

    store = Store(tmp_path / "iso.sqlite")
    store.add_schedule("Rahul", "dopamine", "08:00")
    monkeypatch.setattr(server, "store", store)
    return server


def test_audio_goes_to_gemini_and_words_come_back(app, monkeypatch):
    session = FakeSession([("partial", "Add"), ("partial", "Add Rahul"), ("final", "Add Rahul."), ("final", "At 8 AM.")])
    vocab = []
    monkeypatch.setattr(app.gemini, "live_connect", connector(session, vocab))
    client = TestClient(app.app)
    with client.websocket_connect("/api/transcribe/live") as ws:
        ws.send_bytes(b"\x00\x01" * 1600)
        ws.send_text('{"type": "end"}')
        messages = []
        while True:
            message = ws.receive_json()
            messages.append(message)
            if message["type"] in {"done", "error"}:
                break
    assert [m["type"] for m in messages] == ["partial", "partial", "final", "final", "done"]
    assert messages[-1]["text"] == "Add Rahul. At 8 AM."
    assert session.audio == [(b"\x00\x01" * 1600, "audio/pcm;rate=16000")]
    assert "Rahul" in vocab[0] and "dopamine" in vocab[0]


def test_done_falls_back_to_the_last_partial(app, monkeypatch):
    monkeypatch.setattr(app.gemini, "live_connect", connector(FakeSession([("partial", "Add Rahul")])))
    client = TestClient(app.app)
    with client.websocket_connect("/api/transcribe/live") as ws:
        ws.send_text('{"type": "end"}')
        assert ws.receive_json()["type"] == "partial"
        assert ws.receive_json() == {"type": "done", "text": "Add Rahul"}


def test_a_failing_connection_reports_an_error(app, monkeypatch):
    def broken(vocabulary):
        raise RuntimeError("quota")

    monkeypatch.setattr(app.gemini, "live_connect", broken)
    client = TestClient(app.app)
    with client.websocket_connect("/api/transcribe/live") as ws:
        assert ws.receive_json()["type"] == "error"


def test_live_is_refused_without_a_key_or_from_another_site(app, monkeypatch):
    from starlette.websockets import WebSocketDisconnect

    client = TestClient(app.app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/transcribe/live", headers={"origin": "http://evil.example"}):
            pass
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/transcribe/live"):
            pass


def test_health_reports_live(app):
    async def run():
        import httpx

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app), base_url="http://test", trust_env=False) as client:
            return (await client.get("/api/health")).json()["capabilities"]

    assert asyncio.run(run())["transcribe_live"] is True


def test_quota_errors_get_a_clear_message(app, monkeypatch):
    def broken(vocabulary):
        raise RuntimeError("1011 None. Your prepayment credits are depleted.")

    monkeypatch.setattr(app.gemini, "live_connect", broken)
    client = TestClient(app.app)
    with client.websocket_connect("/api/transcribe/live") as ws:
        assert ws.receive_json() == {"type": "error", "message": "Live transcription is out of credits or quota."}
