"""Record the app for the demo video: the real UI at 1440x810, no overlays or captions.

    python demo/make_footage.py

Starts its own server on a temporary database, drives Chrome (microphone from a prepared clip),
and writes public/footage/app.mp4 plus public/footage/timeline.json (chapter start/end in
seconds) into the video project. Run demo/make_narration.py first: chapters are paced to it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import soundfile as sf
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from video_script import PUBLIC, VOICE_LINE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("DEMO_PORT", "8130"))
BASE = f"http://127.0.0.1:{PORT}"
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
SIZE = {"width": 1440, "height": 810}  # shown 1:1 inside the video, so the UI text stays sharp


def tts(text: str, voice: str, silence_after: float = 0.0) -> Path:
    from kokoro import KPipeline

    audio = np.concatenate([np.asarray(c) for _, _, c in KPipeline(lang_code="a")(text, voice=voice, speed=0.95)])
    audio = np.concatenate([np.zeros(int(0.4 * 24000)), audio, np.zeros(int(silence_after * 24000))])
    path = Path(tempfile.mkdtemp(prefix="clip-")) / "clip.wav"
    sf.write(path, audio.astype("float32"), 24000, subtype="PCM_16")
    return path


def start_server() -> subprocess.Popen:
    env = {
        **os.environ,
        "DOSE_DB": str(Path(tempfile.mkdtemp(prefix="demo-db-")) / "demo.sqlite"),
        "PYTHONPATH": str(ROOT / "src"),
        "DOSE_AUTH_PROVIDER": "local",
        "GEMINI_LIVE": "0",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "dose_check.server:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    import httpx

    for _ in range(60):
        try:
            if httpx.get(f"{BASE}/api/health", timeout=1).status_code == 200:
                return process
        except Exception:
            time.sleep(0.5)
    process.kill()
    raise RuntimeError("server did not start")


def main() -> None:
    lengths = json.loads((PUBLIC / "audio" / "lengths.json").read_text())
    voice = tts(VOICE_LINE, "am_adam", silence_after=12)
    server = start_server()
    video_dir = Path(tempfile.mkdtemp(prefix="footage-"))
    chapters: dict[str, dict[str, float]] = {}
    alexa: dict[str, object] = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=CHROME,
                args=["--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                      f"--use-file-for-fake-audio-capture={voice}"],
            )
            context = browser.new_context(
                viewport=SIZE, record_video_dir=str(video_dir), record_video_size=SIZE, permissions=["microphone"],
            )
            zero = time.time()
            page = context.new_page()
            # Dose reminders come from the real clock, so one could pop up in the middle of another
            # scene. Keep them quiet until the reminder chapter, where they are the point.
            show_reminders = {"on": False}

            def reminders(route):
                if show_reminders["on"]:
                    route.continue_()
                else:
                    route.fulfill(json={"ok": True, "reminders": [], "speech": ""})

            page.route("**/api/reminders", reminders)
            now = lambda: time.time() - zero

            def chapter(key, actions):
                start = now()
                actions()
                # Never shorter than the narration for this chapter.
                need = lengths[key] + 0.8 - (now() - start)
                if need > 0:
                    page.wait_for_timeout(int(need * 1000))
                chapters[key] = {"start": round(start, 2), "end": round(now(), 2)}

            def say(text, delay=42):
                box = page.locator("#utterance")
                box.click()
                box.type(text, delay=delay)
                page.wait_for_timeout(300)
                page.click("button:has-text('Ask')")

            def reply(n):
                page.wait_for_selector(f".bubble.assistant >> nth={n}", timeout=60000)
                page.wait_for_timeout(1100)

            page.goto(f"{BASE}/login")
            page.wait_for_selector(".login-card")
            page.wait_for_timeout(1200)

            def setup():
                page.fill("input[type=email]", f"caregiver{int(time.time())}@example.com")
                page.wait_for_timeout(300)
                page.fill("input[type=password]", "correct horse battery")
                page.fill("input[placeholder='Sharma family']", "Sharma family")
                page.wait_for_timeout(500)
                page.click("text=Create household")
                page.wait_for_selector(".sidebar")
                page.wait_for_timeout(700)
                for name, med in (("Mom", "lisinopril"), ("Raj", "")):
                    page.click("text=+ Add person")
                    page.fill("input[placeholder=Raj]", name)
                    page.wait_for_timeout(300)
                    page.click("button:has-text('Add person') >> nth=-1")
                    page.wait_for_selector(".modal.wide[open]")
                    page.wait_for_timeout(400)
                    if med:
                        page.click("text=+ Add medicine")
                        page.fill("input[placeholder=lisinopril]", med)
                        page.click("text=+ Another time")
                        page.locator("input[type=time]").nth(1).fill("20:00")
                        page.wait_for_timeout(700)
                        page.click("button:has-text('Add medicine') >> nth=-1")
                        page.wait_for_selector(".meds li")
                        page.wait_for_timeout(900)
                    page.click("text=Close")
                    page.wait_for_timeout(300)
            chapter("setup", setup)

            def voice_add():
                page.hover("button:has-text('Speak')")
                page.click("button:has-text('Speak')")
                for _ in range(80):
                    page.wait_for_timeout(250)
                    if page.locator(".bubble.user").count():
                        break
                page.wait_for_selector(".bubble.assistant >> nth=1", timeout=60000)
                page.wait_for_timeout(1400)
            chapter("voice", voice_add)

            def chat():
                for n, text in enumerate(["What's due now?", "Mom took her 8 AM medicine", "How did today go?",
                                          "Change Raj's dopamine to 9 AM on weekdays", "Remove dopamine from Raj"], start=2):
                    say(text)
                    reply(n)
            chapter("chat", chat)

            def family():
                page.click("button.role:has-text('Caregiver')")
                page.wait_for_timeout(600)
                say("How is Mom doing?")
                reply(7)
            chapter("family", family)

            def reminder():
                show_reminders["on"] = True
                soon = datetime.now() + timedelta(minutes=10)
                page.click("button.person:has-text('Mom')")
                page.wait_for_selector(".modal.wide[open]")
                page.wait_for_timeout(500)
                page.click("text=+ Add medicine")
                page.fill("input[placeholder=lisinopril]", "metformin")
                page.fill("input[type=time]", soon.strftime("%H:%M"))
                page.wait_for_timeout(700)
                page.click("button:has-text('Add medicine') >> nth=-1")
                page.wait_for_selector(".meds li >> nth=2")
                page.wait_for_timeout(700)
                page.click("text=Close")
                page.wait_for_selector(".reminder", timeout=40000)
                text = page.inner_text(".reminder p")
                clip = tts(text, "af_nova")
                alexa.update(text=text, at=round(now(), 2), clip=str(clip))
                page.wait_for_timeout(5200)
            chapter("reminder", reminder)

            context.close()
            browser.close()
    finally:
        server.kill()

    out = PUBLIC / "footage"
    out.mkdir(parents=True, exist_ok=True)
    source = next(video_dir.glob("*.webm"))
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "14", "-preset", "slow", "-r", "30", "-an", str(out / "app.mp4")],
        check=True,
    )
    reminder_start = chapters["reminder"]["start"]
    subprocess.run(["cp", alexa["clip"], str(PUBLIC / "audio" / "alexa-reminder.wav")], check=True)
    (out / "timeline.json").write_text(json.dumps({
        "chapters": chapters,
        "alexa": {"text": alexa["text"], "offset": round(alexa["at"] - reminder_start, 2)},
    }, indent=2))
    print(json.dumps(chapters), alexa["text"])


if __name__ == "__main__":
    main()
