"""Local speech-to-text with faster-whisper. Audio never leaves this machine.

The browser records a phrase and posts it to /api/transcribe. The household's own
people and medicine names are fed to the model as a prompt so rare words such as
"dopamine" or a family name come out right.
"""

from __future__ import annotations

import importlib.util
import io
import os
import threading
from typing import Any

COMMON_MEDICINES = (
    "aspirin", "metformin", "lisinopril", "amlodipine", "atorvastatin", "levothyroxine",
    "dopamine", "insulin", "paracetamol", "ibuprofen", "omeprazole", "vitamin D",
)

_lock = threading.Lock()
_model: Any = None


def available() -> bool:
    if os.environ.get("DOSE_TRANSCRIBE", "1") == "0":
        return False
    return importlib.util.find_spec("faster_whisper") is not None


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


def transcribe(audio: bytes, prompt: str = "") -> str:
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
