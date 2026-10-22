"""Speech-to-text. Gemini 3.5 Transcribe, ElevenLabs Scribe v2, or local faster-whisper, in that order.

With no cloud key set, audio never leaves this machine. With GEMINI_API_KEY or ELEVENLABS_API_KEY,
each recorded phrase is sent to that service, and a failed or out-of-quota call falls through to the
next transcriber, ending at the local model if it is installed. DOSE_TRANSCRIBE_PROVIDER=local forces
local, and gemini or elevenlabs puts that one first.

The browser records a phrase and posts it to /api/transcribe. The household's own
people and medicine names are fed to the model as a prompt so rare words such as
"dopamine" or a family name come out right.
"""

from __future__ import annotations

import importlib.util
import io
import os
import logging
import threading
import time
from typing import Any

COMMON_MEDICINES = (
    "aspirin", "metformin", "lisinopril", "amlodipine", "atorvastatin", "levothyroxine",
    "dopamine", "insulin", "paracetamol", "ibuprofen", "omeprazole", "vitamin D",
)

_lock = threading.Lock()
_model: Any = None


COOLDOWN_SECONDS = 60
_blocked_until: dict[str, float] = {}

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_MODEL = "scribe_v2"

log = logging.getLogger(__name__)


def _local_installed() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def chain() -> list[str]:
    """Transcribers to try in order: Gemini, then ElevenLabs, then local. A forced one goes first."""
    from dose_check import gemini

    ready = []
    if gemini.enabled():
        ready.append("gemini")
    if os.environ.get("ELEVENLABS_API_KEY", "").strip() and time.monotonic() >= _blocked_until.get("elevenlabs", 0.0):
        ready.append("elevenlabs")
    forced = os.environ.get("DOSE_TRANSCRIBE_PROVIDER", "").lower()
    if forced == "local":
        ready = []
    elif forced in ready:
        ready = [forced] + [name for name in ready if name != forced]
    if _local_installed():
        ready.append("local")
    return ready


def provider() -> str:
    """The transcriber that is tried first."""
    return (chain() or ["local"])[0]


def available() -> bool:
    if os.environ.get("DOSE_TRANSCRIBE", "1") == "0":
        return False
    return bool(chain())


def build_keyterms(people: list[str], medicines: list[str]) -> list[str]:
    terms = [term for term in dict.fromkeys([*people, *medicines, *COMMON_MEDICINES]) if term and len(term) < 50]
    return terms[:100]


def _elevenlabs(audio: bytes, keyterms: list[str] | None) -> str:
    import httpx

    data: dict[str, Any] = {"model_id": ELEVENLABS_MODEL, "language_code": "eng", "tag_audio_events": "false"}
    # Keyterm prompting biases Scribe v2 toward names and drugs but may use extra credits.
    if keyterms and os.environ.get("ELEVENLABS_KEYTERMS", "0") == "1":
        data["keyterms"] = keyterms
    for attempt in (1, 2):
        response = httpx.post(
            ELEVENLABS_URL,
            headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"].strip()},
            data=data,
            files={"file": ("clip.webm", audio, "audio/webm")},
            timeout=30.0,
        )
        if response.status_code == 429 and attempt == 1:  # a burst limit: one short wait often clears it
            time.sleep(float(os.environ.get("ELEVENLABS_RETRY_SECONDS", "2")))
            continue
        response.raise_for_status()
        return str(response.json().get("text", "")).strip()
    raise RuntimeError("unreachable")


def build_prompt(people: list[str], medicines: list[str]) -> str:
    names = ", ".join(dict.fromkeys(people)) or "Mom, Raj"
    drugs = ", ".join(dict.fromkeys([*medicines, *COMMON_MEDICINES]))
    return (
        f"Household medicine schedule. People: {names}. Medicines: {drugs}. "
        f"{(people or ['Raj'])[0]} needs to take dopamine at 8 AM and 8 PM on Monday and Friday. "
        "I took the morning one. What's due now?"
    )


def _load() -> Any:
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(
                os.environ.get("WHISPER_MODEL", "small.en"),
                device=os.environ.get("WHISPER_DEVICE", "cpu"),
                compute_type=os.environ.get("WHISPER_COMPUTE", "int8"),
            )
        return _model


def transcribe(audio: bytes, prompt: str = "", keyterms: list[str] | None = None) -> str:
    from dose_check import gemini

    failure: Exception | None = None
    for name in chain():
        try:
            if name == "gemini":
                return gemini.transcribe(audio, keyterms)
            if name == "elevenlabs":
                return _elevenlabs(audio, keyterms)
            return _local(audio, prompt)
        except Exception as exc:
            failure = exc
            if name == "gemini":
                gemini.note_failure(exc)
            if name == "elevenlabs" and any(code in str(exc) for code in ("429", "402", "401")):
                _blocked_until["elevenlabs"] = time.monotonic() + COOLDOWN_SECONDS
            log.warning("%s transcription failed (%s); trying the next one.", name, exc)
    raise failure or RuntimeError("No transcriber is available.")


def _local(audio: bytes, prompt: str = "") -> str:
    model = _load()
    segments, _ = model.transcribe(
        io.BytesIO(audio),
        language="en",
        beam_size=5,
        temperature=0.0,
        vad_filter=True,
        condition_on_previous_text=False,
        initial_prompt=prompt or None,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    # The vocabulary can leak into near-silent clips; discard an echo of that list only,
    # never the example sentences, which a person may really say.
    vocabulary = prompt.split(" needs to take", 1)[0].lower()
    if text and text.lower().strip(" .,") in vocabulary:
        return ""
    return text
