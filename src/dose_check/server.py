"""Web simulator plus a stateless Streamable HTTP MCP server.

Run from the repo root:

    PYTHONPATH=src uvicorn dose_check.server:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from dose_check.auth import Auth, HouseholdMiddleware, household, COOKIE
from dose_check.db import Store
from dose_check.agent import decide
from dose_check.mcp_client import call_tool
from dose_check import service
from dose_check.speech import maybe_rephrase
from dose_check import transcribe as stt

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
DB_PATH = Path(os.environ.get("DOSE_DB", ROOT / "data" / "dose_check.sqlite"))

store = Store(DB_PATH)
store.seed_if_empty()
auth = Auth(store)


def tenant_store() -> Store:
    hid = household.get()
    if hid is None:
        raise RuntimeError("No authenticated household")
    return store.scoped(hid)

mcp = MCPServer(
    "Family Dose Check",
    instructions=(
        "Household medicine log for an older adult and a family caregiver. "
        "Use the tools to read and update today's doses. "
        "Do not invent doses, times, or reasons. This is not medical advice."
    ),
    version="0.1.0",
)


@mcp.tool()
def list_due_doses(person_name: str = "") -> dict[str, Any]:
    """List doses that are due now or overdue today.

    Args:
        person_name: Optional person, for example Mom. Empty means the whole household.
    """
    return service.list_due_doses(tenant_store(), person_name)


@mcp.tool()
def log_dose(
    status: str,
    person_name: str = "",
    dose_label: str = "",
    time_hint: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Log a dose as taken or skipped.

    Args:
        status: Either taken or skipped.
        person_name: Person the dose belongs to, if known.
        dose_label: Medicine name, if known.
        time_hint: morning, afternoon, evening, tonight, night, or HH:MM.
        reason: Why it was skipped. Leave empty when status is taken.
    """
    return service.log_dose(tenant_store(), status, person_name, dose_label, time_hint, reason)


@mcp.tool()
def dose_status(
    person_name: str = "",
    dose_label: str = "",
    time_hint: str = "",
) -> dict[str, Any]:
    """Say whether a dose was taken, skipped, due, overdue, or later today.

    Args:
        person_name: Person to ask about, if known.
        dose_label: Medicine name, if known.
        time_hint: morning, afternoon, evening, tonight, night, or HH:MM.
    """
    return service.dose_status(tenant_store(), person_name, dose_label, time_hint)


@mcp.tool()
def summarize_day(person_name: str = "") -> dict[str, Any]:
    """Count today's taken, skipped, due, overdue, and later doses.

    Args:
        person_name: Optional person, for example Mom. Empty means the whole household.
    """
    return service.summarize_day(tenant_store(), person_name)


@mcp.tool()
def register_person(name: str) -> dict[str, Any]:
    """Register a person in the household by name.

    Args:
        name: The name to register, for example Raj.
    """
    return service.register_person(tenant_store(), name)


@mcp.tool()
def add_medicine(person_name: str, dose_label: str = "medicine", times: str = "", days: str = "") -> dict[str, Any]:
    """Add one or more medicine times for a person, on every day or chosen days.

    Args:
        person_name: Who needs the medicine.
        dose_label: Medicine name. Use medicine when no specific name was said.
        times: Comma-separated local times, HH:MM, such as 08:00,20:00.
        days: Optional days, such as mon,wed,fri or weekdays or weekends. Empty means every day.
    """
    return service.add_medicine(tenant_store(), person_name, dose_label, times, days)


@mcp.tool()
def remove_medicine(person_name: str = "", dose_label: str = "", time_hint: str = "") -> dict[str, Any]:
    """Remove a medicine from a person's schedule (every time of that medicine unless a time is given).

    Args:
        person_name: Whose medicine to remove.
        dose_label: Medicine name.
        time_hint: Optional morning, afternoon, evening, night, or HH:MM to remove only that time.
    """
    return service.remove_medicine(tenant_store(), person_name, dose_label, time_hint)


@mcp.tool()
def change_medicine(person_name: str, dose_label: str, times: str = "", days: str = "") -> dict[str, Any]:
    """Change the times and/or days of a medicine that is already scheduled.

    Args:
        person_name: Whose medicine to change.
        dose_label: Medicine name.
        times: New comma-separated HH:MM times. Empty keeps the current times.
        days: New days, such as mon,wed,fri or weekdays. Empty keeps the current days.
    """
    return service.change_medicine(tenant_store(), person_name, dose_label, times, days)


@mcp.tool()
def list_medicines(person_name: str = "") -> dict[str, Any]:
    """Say which medicines a person takes, at what times and on which days.

    Args:
        person_name: Optional person. Empty means the whole household.
    """
    return service.list_medicines(tenant_store(), person_name)


@mcp.tool()
def clear_today_log(person_name: str = "") -> dict[str, Any]:
    """Clear today's taken and skipped entries so those doses count as not yet logged.

    Args:
        person_name: Optional person. Empty means the whole household.
    """
    return service.clear_today_log(tenant_store(), person_name)


@mcp.tool()
def remove_person(name: str) -> dict[str, Any]:
    """Remove a person and all of their medicines from the household.

    Args:
        name: The person to remove.
    """
    return service.remove_person(tenant_store(), name)


mcp_http = mcp.streamable_http_app(
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*"],
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
        ],
    ),
)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


async def health(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "capabilities": {
                "aws_enabled": os.environ.get("AWS_ENABLED", "0") == "1",
                "auth_provider": auth.provider,
                "storage": "sqlite",
                "voice_identity": "manual-name-confirmation",
                "transcribe": stt.available(),
            },
            "transport": "streamable-http",
            "mcp_path": "/mcp",
            "tools": [
                "list_due_doses",
                "log_dose",
                "dose_status",
                "summarize_day",
                "register_person",
                "add_medicine",
                "remove_medicine",
                "change_medicine",
                "list_medicines",
                "clear_today_log",
                "remove_person",
            ],
        }
    )


async def today(_: Request) -> JSONResponse:
    return JSONResponse(service.today_board(tenant_store()))


async def schedules(request: Request) -> JSONResponse:
    if request.method == "GET":
        return JSONResponse({"schedules": tenant_store().list_schedules()})
    body = await request.json()
    try:
        created = service.add_schedule(
            tenant_store(),
            str(body.get("person_name", "")),
            str(body.get("dose_label", "")),
            str(body.get("time_local", "")),
            body.get("days"),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(created, status_code=201)


async def update_schedule(request: Request) -> JSONResponse:
    schedule_id = int(request.path_params["schedule_id"])
    body = await request.json()
    try:
        saved = service.update_schedule(
            tenant_store(),
            schedule_id,
            str(body.get("dose_label", "")),
            str(body.get("time_local", "")),
            body.get("days"),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if not saved:
        return JSONResponse({"error": "That dose is not on the schedule."}, status_code=404)
    return JSONResponse({"ok": True})


MAX_AUDIO_BYTES = 8 * 1024 * 1024


async def transcribe_audio(request: Request) -> JSONResponse:
    if not stt.available():
        return JSONResponse({"error": "Local transcription is not installed."}, status_code=503)
    audio = await request.body()
    if not audio:
        return JSONResponse({"error": "No audio received."}, status_code=400)
    if len(audio) > MAX_AUDIO_BYTES:
        return JSONResponse({"error": "That recording is too long."}, status_code=413)
    scoped = tenant_store()
    prompt = stt.build_prompt(scoped.list_people(), [row["dose_label"] for row in scoped.list_schedules()])
    try:
        text = await run_in_threadpool(stt.transcribe, audio, prompt)
    except Exception as exc:
        return JSONResponse({"error": f"Transcription failed: {exc}"}, status_code=500)
    return JSONResponse({"text": text})


async def add_person(request: Request) -> JSONResponse:
    body = await request.json()
    result = service.register_person(tenant_store(), str(body.get("name", "")))
    return JSONResponse(result, status_code=200 if result["ok"] else 400)


async def delete_person(request: Request) -> JSONResponse:
    result = service.remove_person(tenant_store(), request.path_params["name"])
    return JSONResponse(result, status_code=200 if result["ok"] else 404)


async def schedule_item(request: Request) -> JSONResponse:
    if request.method == "PUT":
        return await update_schedule(request)
    return await delete_schedule(request)


async def delete_schedule(request: Request) -> JSONResponse:
    schedule_id = int(request.path_params["schedule_id"])
    if not tenant_store().delete_schedule(schedule_id):
        return JSONResponse({"error": "That dose is not on the schedule."}, status_code=404)
    return JSONResponse({"ok": True})


async def reset_logs(_: Request) -> JSONResponse:
    tenant_store().clear_logs()
    return JSONResponse(service.today_board(tenant_store()))


async def talk(request: Request) -> JSONResponse:
    body = await request.json()
    utterance = str(body.get("utterance", "")).strip()
    speaker = str(body.get("speaker", "older_adult"))
    if speaker not in {"older_adult", "caregiver"}:
        speaker = "older_adult"
    if not utterance:
        return JSONResponse({"error": "Say or type a sentence."}, status_code=400)

    scoped = tenant_store()
    choice = await run_in_threadpool(
        lambda: decide(utterance, speaker, scoped.list_schedules(), scoped.list_people())
    )
    alerts = service.today_board(tenant_store())["alerts"]
    if not choice["tool"]:
        return JSONResponse(
            {
                "speech": choice["speech"],
                "tool": None,
                "arguments": None,
                "result": None,
                "alerts": alerts,
                "used_bedrock": choice["used_bedrock"],
                "protocol": None,
                "transport": "streamable-http",
                "speaker": choice["speaker"],
                "speaker_changed": choice["speaker_changed"],
            }
        )

    port = request.url.port or 80
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        result, protocol = await call_tool(url, choice["tool"], choice["arguments"], headers={
            "Cookie": f"{COOKIE}={request.cookies.get(COOKIE, '').strip()}",
            "Authorization": request.headers.get("authorization", ""),
        })
    except Exception as exc:
        return JSONResponse(
            {"error": f"The MCP call failed: {exc}", "tool": choice["tool"]},
            status_code=502,
        )
    speech, used_bedrock = await run_in_threadpool(maybe_rephrase, result, str(result.get("speech", "")))
    if choice["mode_line"]:
        speech = f"{choice['mode_line']} {speech}"
    return JSONResponse(
        {
            "speech": speech,
            "tool": choice["tool"],
            "arguments": choice["arguments"],
            "result": result,
            "alerts": result.get("alerts", []),
            "used_bedrock": used_bedrock or choice["used_bedrock"],
            "protocol": protocol,
            "transport": "streamable-http",
            "speaker": choice["speaker"],
            "speaker_changed": choice["speaker_changed"],
        }
    )


async def login_page(_: Request) -> FileResponse:
    return FileResponse(WEB / "login.html")


async def index(_: Request) -> FileResponse:
    return FileResponse(WEB / "index.html")


async def agent_page(_: Request) -> FileResponse:
    return FileResponse(WEB / "agent.html")


app = Starlette(
    routes=[
        Route("/login", login_page),
        Route("/api/auth/{action}", auth.endpoint, methods=["GET", "POST"]),
        Route("/api/health", health),
        Route("/api/today", today),
        Route("/api/schedules", schedules, methods=["GET", "POST"]),
        Route("/api/schedules/{schedule_id:int}", schedule_item, methods=["DELETE", "PUT"]),
        Route("/api/transcribe", transcribe_audio, methods=["POST"]),
        Route("/api/people", add_person, methods=["POST"]),
        Route("/api/people/{name}", delete_person, methods=["DELETE"]),
        Route("/api/logs/reset", reset_logs, methods=["POST"]),
        Route("/api/talk", talk, methods=["POST"]),
        Route("/", index),
        Route("/agent", agent_page),
        Mount("/static", app=StaticFiles(directory=WEB)),
        Mount("/", app=mcp_http),
    ],
    lifespan=lifespan,
)
app.add_middleware(HouseholdMiddleware, auth=auth)
