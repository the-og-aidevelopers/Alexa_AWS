"""Choose a dose tool from what was said. Bedrock may choose; the local rules always can."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from jsonschema import validate

from dose_check.intent import HELP, route_utterance

DOSE_TOOLS = (
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
)

_CAREGIVER = re.compile(
    r"\b(?:please\s+)?(?:switch(?:\s+me)?\s+to(?:\s+the)?\s+caregiver(?:\s+mode)?"
    r"|caregiver\s+mode|i am the caregiver|i'?m the caregiver)\b", re.I
)
_OLDER = re.compile(
    r"\b(?:please\s+)?(?:switch(?:\s+me)?\s+to(?:\s+the)?\s+older adult(?:\s+mode)?"
    r"|older adult mode|i am the older adult|i'?m the older adult)\b", re.I
)

_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "list_due_doses",
            "description": "List doses that are due now or overdue today.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "person_name": {"type": "string", "description": "Optional person, for example Mom."},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "log_dose",
            "description": "Log a dose as taken or skipped.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["taken", "skipped"]},
                        "person_name": {"type": "string"},
                        "dose_label": {"type": "string"},
                        "time_hint": {
                            "type": "string",
                            "description": "morning, afternoon, evening, tonight, night, or HH:MM.",
                        },
                        "reason": {"type": "string", "description": "Why it was skipped."},
                    },
                    "required": ["status"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "dose_status",
            "description": "Say whether a dose was taken, skipped, due, overdue, or later today.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "person_name": {"type": "string"},
                        "dose_label": {"type": "string"},
                        "time_hint": {"type": "string"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "summarize_day",
            "description": "Count today's taken, skipped, due, overdue, and later doses.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"person_name": {"type": "string"}},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "register_person",
            "description": "Register a new person. Examples: register Raj, Mr Raj register, register him as Raj.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "add_medicine",
            "description": "Add medicine times when someone needs to take medicine at given times, every day or on chosen days.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "person_name": {"type": "string"},
                        "dose_label": {"type": "string"},
                        "times": {"type": "string", "description": "Comma-separated HH:MM times."},
                        "days": {"type": "string", "description": "Optional days such as mon,wed,fri, weekdays, weekends. Empty means every day."},
                    },
                    "required": ["person_name", "times"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "remove_medicine",
            "description": "Remove a medicine from a person's schedule.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "person_name": {"type": "string"},
                        "dose_label": {"type": "string"},
                        "time_hint": {"type": "string", "description": "Optional HH:MM or morning, afternoon, evening, night."},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "change_medicine",
            "description": "Change the times or days of a medicine already on the schedule.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "person_name": {"type": "string"},
                        "dose_label": {"type": "string"},
                        "times": {"type": "string", "description": "New comma-separated HH:MM times."},
                        "days": {"type": "string", "description": "New days such as mon,wed,fri, weekdays, weekends."},
                    },
                    "required": ["person_name", "dose_label"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_medicines",
            "description": "Say which medicines a person takes, at what times and on which days.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"person_name": {"type": "string"}},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "clear_today_log",
            "description": "Clear today's taken and skipped entries, for one person or the whole household.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"person_name": {"type": "string"}},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "remove_person",
            "description": "Remove a person and all of their medicines from the household.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                }
            },
        }
    },
]

_SYSTEM = (
    "You are Family Dose Check. Pick the one dose tool that matches what the person wants. "
    "Use only the tools you are given. Do not invent a medicine, a time, or a person. "
    "list_due_doses: they ask what is due. "
    "log_dose: they say a dose was taken or skipped. "
    "dose_status: they ask whether a dose was already taken. "
    "summarize_day: they ask how the day went. "
    "register_person: they ask to add or register a person. The name may come before or after register, with or without as. "
    "add_medicine: they say someone needs to take medicine at a time, optionally on certain days. "
    "remove_medicine: they want a medicine taken off someone's schedule. "
    "change_medicine: they want to change the time or days of an existing medicine. "
    "list_medicines: they ask which medicines someone takes and when. "
    "clear_today_log: they ask to clear or reset today's log. "
    "remove_person: they ask to remove a person from the household. "
    "If none of the tools apply, answer in one short sentence and call no tool."
)


def decide(
    utterance: str,
    speaker: str,
    schedules: list[dict[str, Any]],
    people: list[str] | None = None,
    *,
    use_bedrock: bool | None = None,
) -> dict[str, Any]:
    """Return the speaker, the dose tool to call, and any mode-change line."""
    _, remainder = _speaker_change(utterance, speaker)
    changed = _mentions_mode(utterance)
    if _mentions_caregiver(utterance):
        speaker = "caregiver"
    elif _mentions_older(utterance):
        speaker = "older_adult"

    tool_choice = route_utterance(remainder, schedules, people) if remainder else None
    used_bedrock = False
    if tool_choice is None and remainder and _should_use_bedrock(use_bedrock):
        try:
            tool_choice = _bedrock_tool(remainder, speaker, schedules)
            used_bedrock = True
        except Exception:
            tool_choice = None

    mode_line = ""
    if changed:
        mode_line = (
            "Caregiver mode is on."
            if speaker == "caregiver"
            else "Older adult mode is on."
        )
    speech = None
    if tool_choice is None:
        speech = _mode_only_speech(speaker) if changed else HELP
    return {
        "speaker": speaker,
        "speaker_changed": changed,
        "tool": None if tool_choice is None else tool_choice["tool"],
        "arguments": None if tool_choice is None else tool_choice["arguments"],
        "mode_line": mode_line,
        "speech": speech,
        "used_bedrock": used_bedrock,
    }


def _speaker_change(utterance: str, speaker: str) -> tuple[str, str]:
    folded = utterance
    rest = _CAREGIVER.sub(" ", folded)
    rest = _OLDER.sub(" ", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" .,")
    rest = re.sub(r"^(?:and|then|now)\b\s*", "", rest, flags=re.I).strip()
    return speaker, rest


def _mentions_mode(utterance: str) -> bool:
    return _mentions_caregiver(utterance) or _mentions_older(utterance)


def _mentions_caregiver(utterance: str) -> bool:
    return _CAREGIVER.search(utterance.lower().replace("'", "")) is not None


def _mentions_older(utterance: str) -> bool:
    return _OLDER.search(utterance.lower().replace("'", "")) is not None


def _mode_only_speech(speaker: str) -> str:
    if speaker == "caregiver":
        return "Caregiver mode is on. You can ask whether Mom took a dose, or how today went."
    return "Older adult mode is on. You can ask what is due, or say that a dose was taken or skipped."


def _should_use_bedrock(use_bedrock: bool | None) -> bool:
    # Never discover credentials or contact AWS without the global opt-in.
    if os.environ.get("AWS_ENABLED", "0") != "1":
        return False
    if use_bedrock is not None:
        return use_bedrock
    return os.environ.get("AGENT_WITH_BEDROCK", "0") == "1"


def _bedrock_tool(
    utterance: str,
    speaker: str,
    schedules: list[dict[str, Any]],
) -> dict[str, Any] | None:
    import boto3
    from botocore.config import Config

    catalog = ", ".join(
        f"{row['person_name']} takes {row['dose_label']} at {row['time_local']}" for row in schedules
    ) or "no doses scheduled"
    client = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        config=Config(connect_timeout=3, read_timeout=10, retries={"total_max_attempts": 1}),
    )
    response = client.converse(
        modelId=os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0"),
        system=[{"text": _SYSTEM}],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": (
                            f"Speaker: {speaker}. Schedule: {catalog}. "
                            f"The person said: {json.dumps(utterance)}"
                        )
                    }
                ],
            }
        ],
        toolConfig={"tools": _TOOL_SPECS, "toolChoice": {"auto": {}}},
        inferenceConfig={"maxTokens": 200, "temperature": 0},
    )
    calls = [block["toolUse"] for block in response["output"]["message"]["content"] if "toolUse" in block]
    if not calls:
        return None
    if len(calls) != 1 or calls[0].get("name") not in DOSE_TOOLS:
        raise ValueError("Expected one known dose tool.")
    tool_use = calls[0]
    return {"tool": tool_use["name"], "arguments": _clean_args(tool_use["name"], tool_use.get("input"))}


def _clean_args(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    spec = next(item["toolSpec"] for item in _TOOL_SPECS if item["toolSpec"]["name"] == name)
    schema = {**spec["inputSchema"]["json"], "additionalProperties": False}
    validate(raw, schema)

    def text(key: str) -> str:
        value = raw.get(key, "")
        return value.strip()

    if name == "log_dose":
        return {
            "status": text("status"),
            "person_name": text("person_name"),
            "dose_label": text("dose_label"),
            "time_hint": text("time_hint"),
            "reason": text("reason"),
        }
    if name == "dose_status":
        return {
            "person_name": text("person_name"),
            "dose_label": text("dose_label"),
            "time_hint": text("time_hint"),
        }
    if name in {"register_person", "remove_person"}:
        return {"name": text("name")}
    if name == "add_medicine":
        args = {
            "person_name": text("person_name"),
            "dose_label": text("dose_label") or "medicine",
            "times": text("times"),
        }
        if text("days"):
            args["days"] = text("days")
        return args
    if name == "remove_medicine":
        return {"person_name": text("person_name"), "dose_label": text("dose_label"), "time_hint": text("time_hint")}
    if name == "change_medicine":
        args = {"person_name": text("person_name"), "dose_label": text("dose_label"), "times": text("times")}
        if text("days"):
            args["days"] = text("days")
        return args
    return {"person_name": text("person_name")}
