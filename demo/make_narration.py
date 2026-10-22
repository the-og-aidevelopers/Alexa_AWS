"""Voiceover for the demo video: one clip per scene plus word-timed captions for the Remotion project.

    python demo/make_narration.py

Kokoro (local) speaks the lines, and faster-whisper times each word. Output goes to the video
project's public/audio/scenes/.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from video_script import PUBLIC, SCENES  # noqa: E402

CAPTIONS_ONLY = False


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def script_words(text: str, heard: list[dict]) -> list[dict]:
    """Caption words in the script's own spelling (AWS, DynamoDB), timed by what the recognizer heard."""
    tokens = text.split()
    matcher = difflib.SequenceMatcher(None, [norm(t) for t in tokens], [norm(w["text"]) for w in heard], autojunk=False)
    timed: list[tuple[int, int] | None] = [None] * len(tokens)
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            timed[a + k] = (heard[b + k]["startMs"], heard[b + k]["endMs"])
    end_of_speech = heard[-1]["endMs"] if heard else 0
    out = []
    for i, token in enumerate(tokens):
        if timed[i] is None:  # a word the recognizer got wrong: borrow the gap between its neighbours
            left = next((timed[j][1] for j in range(i - 1, -1, -1) if timed[j]), 0)
            right = next((timed[j][0] for j in range(i + 1, len(tokens)) if timed[j]), end_of_speech)
            run = [j for j in range(len(tokens)) if timed[j] is None and left <= (timed[j][0] if timed[j] else left) <= right]
            span = max(right - left, 80)
            gaps = [j for j in range(len(tokens)) if timed[j] is None]
            before = sum(1 for j in gaps if j < i and all(timed[k] is None for k in range(j, i)))
            after = sum(1 for j in gaps if j >= i and all(timed[k] is None for k in range(i, j + 1)))
            count = before + after
            start = left + span * before // count
            timed[i] = (start, start + span // count)
        start, end = timed[i]
        out.append({"text": (" " if i else "") + token, "startMs": start, "endMs": end,
                    "timestampMs": (start + end) // 2, "confidence": 1})
    return out


def main() -> None:
    global CAPTIONS_ONLY
    CAPTIONS_ONLY = "--captions-only" in sys.argv
    from faster_whisper import WhisperModel
    from kokoro import KPipeline

    folder = PUBLIC / "audio" / "scenes"
    folder.mkdir(parents=True, exist_ok=True)
    speaker = KPipeline(lang_code="a")
    timer = WhisperModel("small.en", device="cpu", compute_type="int8")
    lengths = {}
    for index, (scene_id, _kind, text) in enumerate(SCENES, start=1):
        base = folder / f"{index:02d}-{scene_id}"
        if CAPTIONS_ONLY and Path(f"{base}.wav").exists():
            audio, _rate = sf.read(f"{base}.wav")
        else:
            audio = np.concatenate([np.asarray(c) for _, _, c in speaker(text, voice="af_heart", speed=0.95)])
            sf.write(f"{base}.wav", audio, 24000)
        segments, _ = timer.transcribe(f"{base}.wav", language="en", word_timestamps=True)
        words = []
        for segment in segments:
            for word in segment.words:
                words.append({
                    "text": word.word.strip() and (" " if words else "") + word.word.strip(),
                    "startMs": round(word.start * 1000), "endMs": round(word.end * 1000),
                    "timestampMs": round((word.start + word.end) * 500), "confidence": round(word.probability, 3),
                })
        words = script_words(text, words)
        Path(f"{base}.captions.json").write_text(json.dumps(words))
        lengths[scene_id] = len(audio) / 24000
        print(f"{scene_id}: {lengths[scene_id]:.1f}s, {len(words)} words")
    (PUBLIC / "audio" / "lengths.json").write_text(json.dumps(lengths))


if __name__ == "__main__":
    main()
