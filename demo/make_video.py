"""Record the Family Dose Check demo video: drives the real app in Chrome, adds captions and narration.

Usage (from the repo root, with the server's own keys exported if you want cloud voice):
    python demo/make_video.py            # writes demo/out/family-dose-check-demo.mp4

It starts its own server on a temporary database, so your real data is not touched.
Needs: playwright with Chrome, kokoro (narration), soundfile, numpy, ffmpeg, uvicorn.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import wave
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import soundfile as sf
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo" / "out"
PORT = int(os.environ.get("DEMO_PORT", "8130"))
BASE = f"http://127.0.0.1:{PORT}"
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
VOICE_LINE = "Raj needs to take dopamine at 8 AM and 8 PM."

NARRATION = {
    "title": "About half of all prescriptions are taken incorrectly. Family Dose Check is a spoken household medicine log, built for Alexa Plus.",
    "login": "A caregiver creates a private household for the family.",
    "people": "They add the people they care for, and each person's medicines, with the times and the days.",
    "voice": "Anyone can also just say it. The words are transcribed and the right action is chosen.",
    "due": "Asking what is due is a single question.",
    "taken": "Saying that a dose was taken updates the record.",
    "summary": "And the caregiver can ask how the day went, dose by dose.",
    "manage": "Medicines can be changed or removed by chat as well.",
    "family": "One household connects the whole family. Anyone can log anyone's dose, and everyone sees the same record. Here, the caregiver checks on Mom.",
    "reminder": "Ten minutes before a dose, the app announces it. Here Mom's metformin is added for ten minutes from now, and the reminder appears and is spoken.",
    "echo": "With Alexa Plus connected, the same reminder is spoken by Alexa on the Echo in the kitchen, so nobody has to open an app. This part is a concept for now.",
    "connect": "Alexa Plus reaches the app through M C P. The server and the reminder service are built and tested. Connecting Alexa's own proactive notifications is the next step.",
    "mcp": "Every action is a tool on a self-hosted M C P server, over Streamable HTTP, protocol version 2025 11 25.",
    "future": "Next: a photo of a prescription or a pill box will add the medicines automatically. More family members will join the same household with their own sign-in. And reminders will reach every Echo.",
    "close": "Family Dose Check. A household log you can hear. It does not give medical advice.",
}

CAPTION_JS = """
window.__cap = (text) => {
  let el = document.getElementById('__cap');
  if (!el) {
    el = document.createElement('div'); el.id = '__cap';
    el.style.cssText = 'position:fixed;left:50%;bottom:20px;transform:translateX(-50%);max-width:82%;background:rgba(21,52,42,.94);color:#fff;font:600 21px system-ui,sans-serif;padding:11px 22px;border-radius:14px;z-index:99999;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,.3)';
    document.documentElement.appendChild(el);
  }
  el.textContent = text || ''; el.style.display = text ? 'block' : 'none';
};
window.__overlay = (html) => {
  let el = document.getElementById('__ov');
  if (!html) { if (el) el.remove(); return; }
  if (!el) {
    el = document.createElement('div'); el.id = '__ov';
    el.style.cssText = 'position:fixed;inset:0;z-index:99990;font-family:system-ui,sans-serif';
    document.documentElement.appendChild(el);
  }
  el.innerHTML = html;
};
window.__card = (title, sub) => {
  let el = document.getElementById('__card');
  if (!title) { if (el) el.remove(); return; }
  if (!el) {
    el = document.createElement('div'); el.id = '__card';
    el.style.cssText = 'position:fixed;inset:0;background:linear-gradient(160deg,#15342a,#2b6e51);color:#fff;display:grid;place-content:center;text-align:center;gap:18px;font-family:system-ui,sans-serif;z-index:100000;padding:60px';
    document.documentElement.appendChild(el);
  }
  el.innerHTML = '<div style="font-size:64px;font-weight:800;letter-spacing:-1px">' + title + '</div><div style="font-size:28px;opacity:.88;max-width:900px;margin:auto">' + sub + '</div>';
};
"""


ECHO_HTML = '''
<style>
@keyframes glow { 0%,100% { box-shadow: 0 0 25px 6px rgba(37,197,245,.55), inset 0 0 18px rgba(37,197,245,.6);} 50% { box-shadow: 0 0 55px 18px rgba(37,197,245,.85), inset 0 0 30px rgba(37,197,245,.9);} }
</style>
<div style="position:absolute;inset:0;background:radial-gradient(circle at 30% 50%,#1d2f2a,#0b1512);display:flex;align-items:center;justify-content:center;gap:90px;padding:0 80px">
  <div style="position:relative;width:260px;height:260px;flex:none">
    <div style="position:absolute;inset:0;border-radius:50%;background:radial-gradient(circle at 40% 30%,#4a525a,#15191d);box-shadow:0 30px 60px rgba(0,0,0,.6)"></div>
    <div style="position:absolute;left:30px;right:30px;bottom:22px;height:22px;border-radius:50%;border:5px solid #25c5f5;animation:glow 1.8s infinite"></div>
  </div>
  <div style="max-width:620px">
    <div style="display:inline-block;background:#f2b84b;color:#3a2a00;font-weight:800;letter-spacing:.1em;font-size:18px;padding:6px 14px;border-radius:999px;margin-bottom:22px">CONCEPT</div>
    <div style="color:#8fb3a1;font-size:22px;margin-bottom:10px">Alexa+ · Echo in the kitchen · 10 minutes before the dose</div>
    <div style="background:#fff;color:#15342a;font-size:38px;font-weight:700;line-height:1.3;padding:30px 36px;border-radius:30px 30px 30px 6px">“%TEXT%”</div>
  </div>
</div>'''

CONNECT_HTML = '''
<div style="position:absolute;inset:0;background:#f2f7f4;color:#1b2a23;padding:46px 56px">
  <div style="font-size:38px;font-weight:800">How it connects to Alexa+</div>
  <div style="display:flex;align-items:center;gap:16px;margin-top:44px">
    <div style="flex:1;background:#fff;border:3px dashed #b9770e;border-radius:18px;padding:22px;text-align:center"><div style="font-size:26px;font-weight:800">Alexa+ / Echo</div><div style="margin-top:8px;color:#647a6e;font-size:18px">speaks and listens</div><span style="display:inline-block;margin-top:12px;background:#fbf0da;color:#a85f00;font-weight:800;padding:4px 12px;border-radius:999px;font-size:16px">NEXT</span></div>
    <div style="font-size:34px;color:#3a8a68">&#8594;</div>
    <div style="flex:1;background:#fff;border:3px solid #3a8a68;border-radius:18px;padding:22px;text-align:center"><div style="font-size:26px;font-weight:800">MCP</div><div style="margin-top:8px;color:#647a6e;font-size:18px">Streamable HTTP<br>2025-11-25</div><span style="display:inline-block;margin-top:12px;background:#3a8a68;color:#fff;font-weight:800;padding:4px 12px;border-radius:999px;font-size:16px">BUILT</span></div>
    <div style="font-size:34px;color:#3a8a68">&#8594;</div>
    <div style="flex:1;background:#fff;border:3px solid #3a8a68;border-radius:18px;padding:22px;text-align:center"><div style="font-size:26px;font-weight:800">Family Dose Check</div><div style="margin-top:8px;color:#647a6e;font-size:18px">11 tools</div><span style="display:inline-block;margin-top:12px;background:#3a8a68;color:#fff;font-weight:800;padding:4px 12px;border-radius:999px;font-size:16px">BUILT</span></div>
    <div style="font-size:34px;color:#3a8a68">&#8594;</div>
    <div style="flex:1;background:#fff;border:3px solid #3a8a68;border-radius:18px;padding:22px;text-align:center"><div style="font-size:26px;font-weight:800">Household</div><div style="margin-top:8px;color:#647a6e;font-size:18px">people, medicines, log</div><span style="display:inline-block;margin-top:12px;background:#3a8a68;color:#fff;font-weight:800;padding:4px 12px;border-radius:999px;font-size:16px">BUILT</span></div>
  </div>
  <div style="display:flex;align-items:center;gap:16px;margin-top:54px">
    <div style="flex:1;background:#fff;border:3px solid #3a8a68;border-radius:18px;padding:22px;text-align:center"><div style="font-size:26px;font-weight:800">Reminder service</div><div style="margin-top:8px;color:#647a6e;font-size:18px">finds doses due in 10 minutes</div><span style="display:inline-block;margin-top:12px;background:#3a8a68;color:#fff;font-weight:800;padding:4px 12px;border-radius:999px;font-size:16px">BUILT</span></div>
    <div style="font-size:34px;color:#3a8a68">&#8594;</div>
    <div style="flex:1;background:#fff;border:3px dashed #b9770e;border-radius:18px;padding:22px;text-align:center"><div style="font-size:26px;font-weight:800">Alexa+ proactive notification</div><div style="margin-top:8px;color:#647a6e;font-size:18px">&ldquo;Mom's lisinopril is due at 8 AM&rdquo;</div><span style="display:inline-block;margin-top:12px;background:#fbf0da;color:#a85f00;font-weight:800;padding:4px 12px;border-radius:999px;font-size:16px">NEXT</span></div>
    <div style="flex:2"></div>
  </div>
</div>'''

FUTURE_HTML = '''
<div style="position:absolute;inset:0;background:linear-gradient(160deg,#15342a,#2b6e51);color:#fff;padding:50px 60px">
  <div style="font-size:40px;font-weight:800">What comes next</div>
  <div style="display:flex;gap:26px;margin-top:48px">
    <div style="flex:1;background:rgba(255,255,255,.1);border-radius:22px;padding:30px"><div style="font-size:64px">&#128247;</div><div style="font-size:28px;font-weight:800;margin:12px 0">Photo to medicines</div><div style="font-size:20px;opacity:.9;line-height:1.4">Snap a prescription or pill box. The medicines and times are added automatically.</div></div>
    <div style="flex:1;background:rgba(255,255,255,.1);border-radius:22px;padding:30px"><div style="font-size:64px">&#128106;</div><div style="font-size:28px;font-weight:800;margin:12px 0">Whole family, one household</div><div style="font-size:20px;opacity:.9;line-height:1.4">More family members join the same household with their own sign-in. Anyone's dose is logged for everyone.</div></div>
    <div style="flex:1;background:rgba(255,255,255,.1);border-radius:22px;padding:30px"><div style="font-size:64px">&#128276;</div><div style="font-size:28px;font-weight:800;margin:12px 0">Alexa+ reminders</div><div style="font-size:20px;opacity:.9;line-height:1.4">Proactive spoken reminders on every Echo, 10 minutes before each dose.</div></div>
  </div>
</div>'''

_PIPELINE = None


def pipeline():
    global _PIPELINE
    if _PIPELINE is None:
        from kokoro import KPipeline

        _PIPELINE = KPipeline(lang_code="a")
    return _PIPELINE


def speak_clip(text: str, voice_name: str = "af_nova") -> tuple[Path, float]:
    audio = np.concatenate([np.asarray(chunk) for _, _, chunk in pipeline()(text, voice=voice_name, speed=0.95)])
    path = Path(tempfile.mkdtemp(prefix="alexa-")) / "alexa.wav"
    sf.write(path, audio, 24000)
    return path, len(audio) / 24000


def narrate() -> dict[str, tuple[Path, float]]:
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code="a")
    folder = Path(tempfile.mkdtemp(prefix="narration-"))
    clips = {}
    for key, text in NARRATION.items():
        audio = np.concatenate([np.asarray(chunk) for _, _, chunk in pipeline(text, voice="af_heart", speed=0.95)])
        path = folder / f"{key}.wav"
        sf.write(path, audio, 24000)
        clips[key] = (path, len(audio) / 24000)
    return clips


def voice_clip() -> Path:
    """The spoken line, followed by silence so the app's silence detector ends the phrase."""
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code="a")
    audio = np.concatenate([np.asarray(chunk) for _, _, chunk in pipeline(VOICE_LINE, voice="am_adam")])
    audio = np.concatenate([np.zeros(int(0.4 * 24000)), audio, np.zeros(24000 * 12)])
    path = Path(tempfile.mkdtemp(prefix="voice-")) / "voice.wav"
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


def record(clips: dict[str, tuple[Path, float]], voice: Path) -> tuple[Path, list[tuple[str, float]], list]:
    video_dir = Path(tempfile.mkdtemp(prefix="video-"))
    starts: list[tuple[str, float]] = []
    extras: list[tuple[tuple[Path, float], float]] = []
    reminder_text: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            args=["--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                  f"--use-file-for-fake-audio-capture={voice}"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 720}, record_video_dir=str(video_dir),
            record_video_size={"width": 1280, "height": 720}, permissions=["microphone"],
        )
        context.add_init_script(CAPTION_JS)
        zero = time.time()
        page = context.new_page()

        def scene(key, caption, actions=None):
            start = time.time() - zero
            starts.append((key, start))
            page.evaluate("(t) => window.__cap && window.__cap(t)", caption)
            if actions:
                actions()
            remaining = clips[key][1] + 0.7 - (time.time() - zero - start)
            if remaining > 0:
                page.wait_for_timeout(int(remaining * 1000))

        def say(text, delay=38):
            box = page.locator("#utterance")
            box.click()
            box.type(text, delay=delay)
            page.wait_for_timeout(250)
            page.click("button:has-text('Ask')")

        def reply(n):
            page.wait_for_selector(f".bubble.assistant >> nth={n}", timeout=60000)
            page.wait_for_timeout(900)

        page.goto(f"{BASE}/login")
        page.wait_for_selector(".login-card")
        page.evaluate("window.__card('Family Dose Check', 'A spoken household medicine log for Alexa+')")
        scene("title", "")
        page.evaluate("window.__card('')")

        def create():
            page.fill("input[type=email]", f"caregiver{int(time.time())}@example.com")
            page.wait_for_timeout(300)
            page.fill("input[type=password]", "correct horse battery")
            page.fill("input[placeholder='Sharma family']", "Sharma family")
            page.wait_for_timeout(500)
            page.click("text=Create household")
            page.wait_for_selector(".sidebar")
        scene("login", "A caregiver creates a private household", create)

        def people():
            for name, med, times in (("Mom", "lisinopril", 2), ("Raj", "", 0)):
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
        scene("people", "Add people and their medicines: times and days", people)

        def voice_add():
            page.hover("button:has-text('Speak')")
            page.click("button:has-text('Speak')")
            for _ in range(80):
                page.wait_for_timeout(250)
                if page.locator(".bubble.user").count():
                    break
            page.wait_for_selector(".bubble.assistant >> nth=1", timeout=60000)
            page.wait_for_timeout(1200)
        scene("voice", "Speak it: live words, then the right action", voice_add)

        scene("due", "“What's due now?”", lambda: (say("What's due now?"), reply(2)))
        scene("taken", "“Mom took her 8 AM medicine”", lambda: (say("Mom took her 8 AM medicine"), reply(3)))
        scene("summary", "“How did today go?”", lambda: (say("How did today go?"), reply(4)))

        def manage():
            say("Change Raj's dopamine to 9 AM on weekdays")
            reply(5)
            say("Remove dopamine from Raj")
            reply(6)
        scene("manage", "Change or remove medicines by chat", manage)

        def family():
            page.click("button.role:has-text('Caregiver')")
            page.wait_for_timeout(500)
            say("How is Mom doing?")
            reply(7)
        scene("family", "One household, many people. Anyone can log anyone's dose", family)

        def reminder():
            soon = datetime.now() + timedelta(minutes=10)
            page.click("button.person:has-text('Mom')")
            page.wait_for_selector(".modal.wide[open]")
            page.click("text=+ Add medicine")
            page.fill("input[placeholder=lisinopril]", "metformin")
            page.fill("input[type=time]", soon.strftime("%H:%M"))
            page.wait_for_timeout(600)
            page.click("button:has-text('Add medicine') >> nth=-1")
            page.wait_for_selector(".meds li >> nth=2")
            page.wait_for_timeout(600)
            page.click("text=Close")
            page.wait_for_selector(".reminder", timeout=40000)
            text = page.inner_text(".reminder p")
            extras.append((speak_clip(text), time.time() - zero))
            reminder_text.append(text)
        scene("reminder", "10 minutes before a dose, the app announces it", reminder)
        page.wait_for_timeout(int((extras[-1][0][1] + 0.8) * 1000))

        scene("echo", "Concept: the same reminder, spoken by Alexa+ on an Echo",
              lambda: page.evaluate("(html) => window.__overlay(html)", ECHO_HTML.replace("%TEXT%", reminder_text[-1])))
        page.evaluate("window.__overlay('')")

        scene("connect", "How it connects: MCP today, Alexa+ proactive delivery next",
              lambda: page.evaluate("(html) => window.__overlay(html)", CONNECT_HTML))

        def mcp():
            page.evaluate("window.__overlay('')")
            page.evaluate("""async () => {
              const data = await (await fetch('/api/health')).json();
              const panel = document.createElement('div');
              panel.id = '__mcp';
              panel.style.cssText = 'position:fixed;inset:0;background:#f2f7f4;color:#1b2a23;font-family:system-ui,sans-serif;padding:60px 70px;z-index:99990';
              panel.innerHTML = '<div style="font-size:38px;font-weight:800;margin-bottom:10px">Self-hosted MCP server</div>'
                + '<div style="font-size:24px;color:#647a6e;margin-bottom:34px">Streamable HTTP at ' + data.mcp_path + ' · protocol 2025-11-25</div>';
              const box = document.createElement('div');
              box.style.cssText = 'display:flex;flex-wrap:wrap;gap:14px';
              data.tools.forEach((tool) => {
                const chip = document.createElement('code');
                chip.textContent = tool;
                chip.style.cssText = 'background:#fff;border:2px solid #3a8a68;border-radius:14px;padding:12px 20px;font-size:26px';
                box.appendChild(chip);
              });
              panel.appendChild(box);
              document.documentElement.appendChild(panel);
            }""")
        scene("mcp", "Every action is an MCP tool", mcp)

        def future():
            page.evaluate("document.getElementById('__mcp') && document.getElementById('__mcp').remove()")
            page.evaluate("(html) => window.__overlay(html)", FUTURE_HTML)
        scene("future", "What comes next", future)

        def close():
            page.evaluate("window.__overlay('')")
            page.evaluate("window.__card('Family Dose Check', 'A household log you can hear. Not medical advice.')")
        scene("close", "", close)

        context.close()
        browser.close()
    video = next(video_dir.glob("*.webm"))
    return video, starts, extras


def assemble(video: Path, starts, clips, extras) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    final = OUT / "family-dose-check-demo.mp4"
    inputs, filters, labels = ["-i", str(video)], [], []
    for index, (key, start) in enumerate(starts, start=1):
        inputs += ["-i", str(clips[key][0])]
        delay = int(max(start, 0) * 1000)
        filters.append(f"[{index}:a]adelay={delay}|{delay},volume=1.0[a{index}]")
        labels.append(f"[a{index}]")
    for (clip, _length), start in extras:
        index = len(labels) + 1
        inputs += ["-i", str(clip)]
        delay = int(max(start, 0) * 1000)
        filters.append(f"[{index}:a]adelay={delay}|{delay},volume=1.0[a{index}]")
        labels.append(f"[a{index}]")
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0[audio]")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters),
         "-map", "0:v", "-map", "[audio]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
         "-preset", "medium", "-c:a", "aac", "-b:a", "160k", "-shortest", str(final)],
        check=True,
    )
    return final


def main() -> None:
    clips = narrate()
    voice = voice_clip()
    server = start_server()
    try:
        video, starts, extras = record(clips, voice)
    finally:
        server.kill()
    final = assemble(video, starts, clips, extras)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(final)],
        capture_output=True, text=True,
    )
    print(f"{final}  ({float(probe.stdout):.0f} seconds)")


if __name__ == "__main__":
    main()
