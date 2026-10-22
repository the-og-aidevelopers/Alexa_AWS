"""Relay a browser's microphone stream to Gemini's live transcriber and send the words back.

Messages from the browser: binary frames of 16 kHz, 16-bit, mono PCM, then {"type": "end"}.
Messages to the browser: {"type": "partial"|"final", "text"}, then {"type": "done", "text"}
or {"type": "error", "message"}. The Gemini key stays on the server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable

log = logging.getLogger(__name__)

IDLE_AFTER_END = 1.0   # seconds without new text, after the browser says it is done
MAX_AFTER_END = 4.0


async def relay(ws: Any, vocabulary: list[str], connect: Callable[[list[str]], Any]) -> None:
    from google.genai import types

    finals: list[str] = []
    state = {"interim": "", "last": time.monotonic()}

    async def read_gemini(session: Any) -> None:
        while True:
            async for response in session.receive():
                content = getattr(response, "server_content", None)
                if not content:
                    continue
                interim = getattr(content, "interim_input_transcription", None)
                final = getattr(content, "input_transcription", None)
                if interim and interim.text:
                    state["interim"] = interim.text.strip()
                    state["last"] = time.monotonic()
                    await ws.send_json({"type": "partial", "text": state["interim"]})
                if final and final.text and final.text.strip():
                    finals.append(final.text.strip())
                    state["interim"] = ""
                    state["last"] = time.monotonic()
                    await ws.send_json({"type": "final", "text": finals[-1]})

    async def read_browser(session: Any) -> str:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return "gone"
            if message.get("bytes"):
                await session.send_realtime_input(
                    audio=types.Blob(data=message["bytes"], mime_type="audio/pcm;rate=16000")
                )
            elif message.get("text"):
                try:
                    kind = json.loads(message["text"]).get("type")
                except ValueError:
                    kind = None
                if kind == "end":
                    await session.send_realtime_input(audio_stream_end=True)
                    return "end"

    try:
        async with connect(vocabulary) as session:
            reader = asyncio.create_task(read_gemini(session))
            try:
                reason = await read_browser(session)
                if reason == "end":
                    ended = time.monotonic()
                    state["last"] = ended
                    while time.monotonic() - ended < MAX_AFTER_END:
                        if reader.done() or time.monotonic() - state["last"] > IDLE_AFTER_END:
                            break
                        await asyncio.sleep(0.1)
            finally:
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
            if reason == "gone":
                return
        text = " ".join(finals).strip() or state["interim"]
        await ws.send_json({"type": "done", "text": text})
    except Exception as exc:  # network, quota, or a closed browser
        log.warning("Live transcription failed: %s", exc)
        detail = str(exc).lower()
        message = (
            "Live transcription is out of credits or quota."
            if any(word in detail for word in ("credit", "quota", "429", "billing", "exhausted"))
            else "Live transcription failed."
        )
        try:
            await ws.send_json({"type": "error", "message": message})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
