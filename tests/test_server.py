import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from dose_check.mcp_client import list_tool_names

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def server(tmp_path, request):
    port = _free_port()
    env = {
        **dict(**{key: value for key, value in __import__("os").environ.items()}),
        "DOSE_DB": str(tmp_path / "dose.sqlite"),
        "PYTHONPATH": str(ROOT / "src") + ":" + __import__("os").environ.get("PYTHONPATH", ""),
        "DOSE_AUTH_PROVIDER": getattr(request, "param", "demo"),
        "AWS_ENABLED": "0",
        "SPEAK_WITH_BEDROCK": "0",
        "AGENT_WITH_BEDROCK": "0",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "dose_check.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    last_error = ""
    while time.time() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"Server exited early:\n{output}")
        try:
            response = httpx.get(f"{base}/api/health", timeout=0.5, trust_env=False)
            if response.status_code == 200:
                break
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(0.15)
    else:
        process.terminate()
        output = process.stdout.read() if process.stdout else ""
        raise RuntimeError(f"Server did not start: {last_error}\n{output}")
    try:
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def test_talk_goes_through_streamable_http(server):
    page = httpx.get(f"{server}/", timeout=5, trust_env=False)
    assert page.status_code == 200
    assert "Family Dose Check" in page.text

    import anyio

    names, protocol = anyio.run(list_tool_names, f"{server}/mcp")
    assert names == [
        "list_due_doses",
        "log_dose",
        "dose_status",
        "summarize_day",
        "register_person",
        "add_medicine",
    ]
    assert protocol >= "2025-11-25"

    reply = httpx.post(
        f"{server}/api/talk",
        json={"utterance": "What's due now?", "speaker": "older_adult"},
        timeout=15, trust_env=False,
    )
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["tool"] == "list_due_doses"
    assert body["transport"] == "streamable-http"
    assert body["protocol"] >= "2025-11-25"
    assert body["speech"]

    logged = httpx.post(
        f"{server}/api/talk",
        json={"utterance": "I took the morning one", "speaker": "older_adult"},
        timeout=15, trust_env=False,
    )
    assert logged.status_code == 200, logged.text
    assert logged.json()["tool"] == "log_dose"
    assert logged.json()["result"]["ok"] is True

