import threading

import anyio
import httpx
import pytest


@pytest.mark.parametrize("stage", ["decide", "rephrase"])
def test_slow_provider_does_not_block_health(monkeypatch, tmp_path, stage):
    monkeypatch.setenv("DOSE_DB", str(tmp_path / "concurrency.sqlite"))
    monkeypatch.setenv("DOSE_AUTH_PROVIDER", "demo")
    from dose_check import server
    from dose_check.db import Store

    monkeypatch.setattr(server, "store", Store(tmp_path / "isolated.sqlite"))
    entered = threading.Event()
    release = threading.Event()
    choice = {
        "tool": "list_due_doses" if stage == "rephrase" else None,
        "arguments": {}, "speech": "Ready.", "used_bedrock": False,
        "speaker": "older_adult", "speaker_changed": False, "mode_line": "",
    }

    def decide(*args):
        if stage == "decide":
            entered.set()
            assert release.wait(3), "Health request was blocked by the model call"
        return choice

    def rephrase(*args):
        entered.set()
        assert release.wait(3), "Health request was blocked by speech rephrasing"
        return "Ready.", False

    async def call_tool(*args, **kwargs):
        return {"speech": "Ready."}, "2025-11-25"

    monkeypatch.setattr(server, "decide", decide)
    monkeypatch.setattr(server, "maybe_rephrase", rephrase)
    monkeypatch.setattr(server, "call_tool", call_tool)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app), base_url="http://test", trust_env=False,
        ) as client:
            async def talk():
                response = await client.post("/api/talk", json={"utterance": "What's due now?"})
                assert response.status_code == 200

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(talk)
                try:
                    with anyio.fail_after(2):
                        while not entered.is_set():
                            await anyio.sleep(0.01)
                        response = await client.get("/api/health")
                        assert response.status_code == 200
                finally:
                    release.set()

    anyio.run(run)
