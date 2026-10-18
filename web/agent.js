const statusLine = document.querySelector("#status");
const orb = document.querySelector("#orb");
const canvas = document.querySelector("#waves");
const caption = document.querySelector("#caption");
const transcript = document.querySelector("#transcript");
const ctx = canvas.getContext("2d");

let speaker = "older_adult";
let recognizing = false;
let mode = "idle";
let meterStream = null;
let audioContext = null;
let analyser = null;
const meterBins = new Uint8Array(128);

const labels = {
  idle: "Tap the circle to talk",
  listening: "Listening",
  thinking: "One moment",
  speaking: "Speaking",
};

orb.addEventListener("click", toggleMic);
draw();

function setMode(next) {
  mode = next;
  orb.dataset.state = next;
  orb.setAttribute("aria-pressed", next === "listening" ? "true" : "false");
  statusLine.textContent = labels[next];
}

const listener = new AutoListener({
  onState(active) {
    recognizing = active;
    if (active) {
      setMode("listening");
      startMeter();
    } else {
      stopMeter();
      if (mode === "listening") setMode("idle");
    }
  },
  onTranscript(text) { caption.textContent = text; },
  onStatus(text) { if (text) statusLine.textContent = text; },
  onUtterance: sendUtterance,
  onError(text) { statusLine.textContent = text; },
});

function toggleMic() {
  if (mode === "thinking") return;
  if (listener.active) { listener.finish(); return; }
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  listener.start();
}

window.addEventListener("pagehide", () => listener.cancel());

async function sendUtterance(raw) {
  if (mode === "thinking") return;
  listener.cancel();
  const utterance = raw.trim();
  if (!utterance) return;
  caption.textContent = "";
  appendLine("You", utterance, "you");
  setMode("thinking");
  try {
    const response = await fetch("/api/talk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ utterance, speaker }),
    });
    const body = await response.json();
    if (!response.ok) {
      setMode("idle");
      statusLine.textContent = body.error || "The request failed.";
      return;
    }
    if (body.speaker) speaker = body.speaker;
    appendLine("Family Dose Check", body.speech, "agent");
    await speak(body.speech);
  } catch (error) {
    setMode("idle");
    statusLine.textContent = "The agent could not reach the server.";
  }
}

function appendLine(who, text, kind) {
  const item = document.createElement("li");
  item.className = `line ${kind}`;
  const label = document.createElement("p");
  label.className = "who";
  label.textContent = who;
  const message = document.createElement("p");
  message.textContent = text;
  item.append(label, message);
  transcript.append(item);
  transcript.scrollTop = transcript.scrollHeight;
}

function speak(text) {
  return new Promise((resolve) => {
    if (!window.speechSynthesis || recognizing) {
      setMode("idle");
      resolve();
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95;
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (mode === "speaking") setMode("idle");
      resolve();
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    const timer = setTimeout(finish, Math.min(20000, Math.max(1600, text.length * 75)));
    setMode("speaking");
    window.speechSynthesis.speak(utterance);
  });
}

let meterGeneration = 0;

async function startMeter() {
  const generation = ++meterGeneration;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    if (generation !== meterGeneration || !recognizing) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    meterStream = stream;
    audioContext = audioContext || new AudioContext();
    if (audioContext.state === "suspended") await audioContext.resume();
    if (generation !== meterGeneration || !recognizing) return;
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    audioContext.createMediaStreamSource(meterStream).connect(analyser);
  } catch (error) {
    if (generation === meterGeneration) stopMeter();
  }
}

function stopMeter() {
  meterGeneration += 1;
  if (meterStream) {
    meterStream.getTracks().forEach((track) => track.stop());
    meterStream = null;
  }
  analyser = null;
}

function draw() {
  const ratio = window.devicePixelRatio || 1;
  const size = 360;
  if (canvas.width !== size * ratio) {
    canvas.width = size * ratio;
    canvas.height = size * ratio;
  }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, size, size);
  if (analyser && mode === "listening") analyser.getByteFrequencyData(meterBins);
  const now = performance.now() / 1000;
  const bars = 56;
  const cx = size / 2;
  const cy = size / 2;
  const color = mode === "listening" ? "#e7b15a" : mode === "speaking" ? "#8fd0b0" : "#6f8f80";
  ctx.strokeStyle = color;
  ctx.lineCap = "round";
  ctx.lineWidth = 3;
  for (let i = 0; i < bars; i += 1) {
    const angle = (i / bars) * Math.PI * 2 - Math.PI / 2;
    let amp = 5 + Math.abs(Math.sin(now * 1.3 + i * 0.18)) * 5;
    if (mode === "listening") {
      const bin = analyser ? meterBins[i % meterBins.length] / 255 : Math.abs(Math.sin(now * 7 + i));
      amp = 8 + bin * 48;
    } else if (mode === "speaking") {
      amp = 8 + Math.abs(Math.sin(now * 9 + i * 0.55)) * 34;
    } else if (mode === "thinking") {
      amp = 7 + Math.abs(Math.sin(now * 3 + i * 0.25)) * 8;
    }
    const inner = 92;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * inner, cy + Math.sin(angle) * inner);
    ctx.lineTo(cx + Math.cos(angle) * (inner + amp), cy + Math.sin(angle) * (inner + amp));
    ctx.stroke();
  }
  requestAnimationFrame(draw);
}

document.addEventListener("dose-say", (event) => {
  if (typeof event.detail === "string") sendUtterance(event.detail);
});
document.addEventListener("dose-mode", (event) => {
  if (labels[event.detail]) setMode(event.detail);
});
document.documentElement.dataset.agent = "ready";

