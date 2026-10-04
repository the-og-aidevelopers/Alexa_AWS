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
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from dose_check.db import Store
from dose_check.agent import decide
from dose_check.mcp_client import call_tool
from dose_check import service
from dose_check.speech import maybe_rephrase

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
DB_PATH = Path(os.environ.get("DOSE_DB", ROOT / "data" / "dose_check.sqlite"))

store = Store(DB_PATH)
store.seed_if_empty()

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
    return service.list_due_doses(store, person_name)


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
    return service.log_dose(store, status, person_name, dose_label, time_hint, reason)


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
    return service.dose_status(store, person_name, dose_label, time_hint)


@mcp.tool()
def summarize_day(person_name: str = "") -> dict[str, Any]:
    """Count today's taken, skipped, due, overdue, and later doses.

    Args:
        person_name: Optional person, for example Mom. Empty means the whole household.
    """
    return service.summarize_day(store, person_name)


@mcp.tool()
def register_person(name: str) -> dict[str, Any]:
    """Register a person in the household by name.

    Args:
        name: The name to register, for example Raj.
    """
    return service.register_person(store, name)


@mcp.tool()
def add_medicine(person_name: str, dose_label: str = "medicine", times: str = "") -> dict[str, Any]:
    """Add one or more daily medicine times for a person.

    Args:
        person_name: Who needs the medicine.
        dose_label: Medicine name. Use medicine when no specific name was said.
        times: Comma-separated local times, HH:MM, such as 08:00,20:00.
    """
    return service.add_medicine(store, person_name, dose_label, times)


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
            "transport": "streamable-http",
            "mcp_path": "/mcp",
            "tools": [
                "list_due_doses",
                "log_dose",
                "dose_status",
                "summarize_day",
                "register_person",
                "add_medicine",
            ],
        }
    )


async def today(_: Request) -> JSONResponse:
    return JSONResponse(service.today_board(store))


async def schedules(request: Request) -> JSONResponse:
    if request.method == "GET":
        return JSONResponse({"schedules": store.list_schedules()})
    body = await request.json()
    try:
        created = service.add_schedule(
            store,
            str(body.get("person_name", "")),
            str(body.get("dose_label", "")),
            str(body.get("time_local", "")),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(created, status_code=201)


async def delete_schedule(request: Request) -> JSONResponse:
    schedule_id = int(request.path_params["schedule_id"])
    if not store.delete_schedule(schedule_id):
        return JSONResponse({"error": "That dose is not on the schedule."}, status_code=404)
    return JSONResponse({"ok": True})


async def reset_logs(_: Request) -> JSONResponse:
    store.clear_logs()
    return JSONResponse(service.today_board(store))


async def talk(request: Request) -> JSONResponse:
    body = await request.json()
    utterance = str(body.get("utterance", "")).strip()
    speaker = str(body.get("speaker", "older_adult"))
    if speaker not in {"older_adult", "caregiver"}:
        speaker = "older_adult"
    if not utterance:
        return JSONResponse({"error": "Say or type a sentence."}, status_code=400)

    choice = await run_in_threadpool(decide, utterance, speaker, store.list_schedules())
    alerts = service.today_board(store)["alerts"]
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
        result, protocol = await call_tool(url, choice["tool"], choice["arguments"])
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


async def index(_: Request) -> FileResponse:
    return FileResponse(WEB / "index.html")


async def agent_page(_: Request) -> FileResponse:
    return FileResponse(WEB / "agent.html")


app = Starlette(
    routes=[
        Route("/api/health", health),
        Route("/api/today", today),
        Route("/api/schedules", schedules, methods=["GET", "POST"]),
        Route("/api/schedules/{schedule_id:int}", delete_schedule, methods=["DELETE"]),
        Route("/api/logs/reset", reset_logs, methods=["POST"]),
        Route("/api/talk", talk, methods=["POST"]),
        Route("/", index),
        Route("/agent", agent_page),
        Mount("/static", app=StaticFiles(directory=WEB)),
        Mount("/", app=mcp_http),
    ],
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"],
)
