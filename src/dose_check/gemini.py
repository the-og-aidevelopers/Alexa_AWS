"""Gemini: speech-to-text (gemini-3.5-transcribe) and sentence-to-tool routing (function calling).

Set GEMINI_API_KEY (or GOOGLE_API_KEY) to turn both on. Audio and text then go to Google; on the free
tier Google may use submitted content to improve its products. GEMINI_ROUTING=0 keeps transcription
but turns the routing off. Anything that fails falls back to the local rules and the other
transcribers, so the app keeps working without the network.
"""

from __future__ import annotations

import base64
import io
import json
import os
import threading
import time
import wave
from typing import Any

TRANSCRIBE_MODEL = "gemini-3.5-transcribe"
LIVE_MODEL = "gemini-3.5-transcribe-live"
DEFAULT_ROUTER_MODEL = "gemini-3.5-flash-lite"
TIMEOUT_MS = 15000

_lock = threading.Lock()
_client: Any = None


COOLDOWN_SECONDS = 600
_blocked_until = 0.0


def note_failure(error: Exception) -> None:
    """After a quota or billing error, skip Gemini for a while instead of failing on every phrase."""
    global _blocked_until
    detail = str(error).lower()
    if any(word in detail for word in ("402", "429", "credit", "quota", "exhausted", "billing")):
        _blocked_until = time.monotonic() + COOLDOWN_SECONDS


def blocked() -> bool:
    return time.monotonic() < _blocked_until


def reset() -> None:
    global _blocked_until
    _blocked_until = 0.0


def api_key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def enabled() -> bool:
    return bool(api_key()) and not blocked()


def routing_enabled() -> bool:
    return enabled() and os.environ.get("GEMINI_ROUTING", "1") != "0"


def live_enabled() -> bool:
    """Streaming transcription: words arrive while the person is still speaking."""
    return enabled() and os.environ.get("GEMINI_LIVE", "1") != "0"


def live_connect(vocabulary: list[str] | None = None) -> Any:
    """An async context manager for a gemini-3.5-transcribe-live session."""
    from google.genai import types

    transcription = types.AudioTranscriptionConfig(
        language_codes=[os.environ.get("GEMINI_LANGUAGE", "en-US")],
        custom_vocabulary=(vocabulary or [])[:100],
        mode="SMART",
    )
    config = types.LiveConnectConfig(response_modalities=["TEXT"], input_audio_transcription=transcription)
    return _get_client().aio.live.connect(model=LIVE_MODEL, config=config)


def _get_client() -> Any:
    global _client
    with _lock:
        if _client is None:
            from google import genai
            from google.genai import types

            _client = genai.Client(api_key=api_key(), http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        return _client


def _wav(audio: bytes) -> tuple[bytes, str]:
    """Browsers record WebM/Opus. WAV is the safest input, so convert when the decoder is installed."""
    try:
        import numpy as np
        from faster_whisper.audio import decode_audio

        samples = decode_audio(io.BytesIO(audio), sampling_rate=16000)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(pcm)
        return buffer.getvalue(), "audio/wav"
    except Exception:
        return audio, "audio/webm"


def transcribe(audio: bytes, vocabulary: list[str] | None = None) -> str:
    data, mime = _wav(audio)
    config: dict[str, Any] = {
        "language_codes": [os.environ.get("GEMINI_LANGUAGE", "en-US")],
        "mode": {"type": "smart"},
    }
    if vocabulary:
        config["custom_vocabulary"] = vocabulary[:100]
    interaction = _get_client().interactions.create(
        model=TRANSCRIBE_MODEL,
        input=[{"type": "audio", "data": base64.b64encode(data).decode(), "mime_type": mime}],
        generation_config={"transcription_config": config},
        timeout=TIMEOUT_MS / 1000,
    )
    return (interaction.output_text or "").strip()


def instructions(people: list[str], schedules: list[dict[str, Any]], speaker: str) -> str:
    household = {}
    for row in schedules:
        household.setdefault(row["person_name"], []).append(f"{row['dose_label']} at {row['time_local']}")
    catalog = "; ".join(f"{name}: {', '.join(items)}" for name, items in sorted(household.items())) or "no medicines yet"
    return (
        "You are the router for Pillow, a household medicine log. The text comes from speech "
        "recognition, so it may contain mishearings. Choose the ONE tool that is closest to what the person "
        "wants and fill in its arguments. Call no tool only if the request is unrelated to the medicine log.\n"
        "Rules:\n"
        "- Never invent a person, medicine, time or reason. Leave an optional argument empty if it was not said.\n"
        f"- Known people: {', '.join(people) or 'none'}. If the speech clearly means a known person (a close "
        "spelling or sound), use that exact spelling. A new name is allowed for register_person and add_medicine.\n"
        f"- Current schedule: {catalog}.\n"
        "- Possessives mean the owner: \"Mom's 8 AM medicine\" is person Mom.\n"
        "- times: 24-hour HH:MM, comma separated. morning=08:00, afternoon=14:00, evening=20:00, night=21:00.\n"
        "- days: mon,tue,wed,thu,fri,sat,sun, or weekdays, weekends. Leave empty for every day.\n"
        "- dose_label: the medicine name, or \"medicine\" when none was said.\n"
        "- log_dose status is taken or skipped; put a stated reason for skipping in reason.\n"
        "- time_hint is morning, afternoon, evening, tonight, night or HH:MM.\n"
        f"- The speaker is the {speaker.replace('_', ' ')}."
    )


def route(
    utterance: str,
    speaker: str,
    people: list[str],
    schedules: list[dict[str, Any]],
    tool_specs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return {"tool", "arguments"} for the closest tool, or None when no tool fits."""
    from google.genai import types

    declarations = [
        types.FunctionDeclaration(
            name=spec["toolSpec"]["name"],
            description=spec["toolSpec"]["description"],
            parameters_json_schema=spec["toolSpec"]["inputSchema"]["json"],
        )
        for spec in tool_specs
    ]
    config = types.GenerateContentConfig(
        system_instruction=instructions(people, schedules, speaker),
        temperature=0,
        tools=[types.Tool(function_declarations=declarations)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    response = _get_client().models.generate_content(
        model=os.environ.get("GEMINI_MODEL", DEFAULT_ROUTER_MODEL),
        contents=json.dumps(utterance),
        config=config,
    )
    calls = response.function_calls or []
    if not calls:
        return None
    call = calls[0]
    return {"tool": call.name, "arguments": dict(call.args or {})}
