const statusLine = document.querySelector("#status");
const orb = document.querySelector("#orb");
const canvas = document.querySelector("#waves");
const caption = document.querySelector("#caption");
const transcript = document.querySelector("#transcript");
const ctx = canvas.getContext("2d");

let speaker = "older_adult";
let recognizing = false;
let recognition = null;
let guesses = [];
let silenceTimer = null;
let maxTimer = null;
let listenSent = false;
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

async function toggleMic() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    statusLine.textContent = "This browser cannot hear. Use the development page.";
    return;
  }
  if (recognizing && recognition) {
    finishListening();
    return;
  }
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  await startMeter();
  recognition = new Recognition();
  recognition.lang = navigator.language || "en-GB";
  recognition.interimResults = true;
  recognition.maxAlternatives = 5;
  recognition.continuous = true;
  guesses = [];
  listenSent = false;
  caption.textContent = "";
  recognition.onstart = () => {
    recognizing = true;
    setMode("listening");
  };
  recognition.onend = () => {
    if (!listenSent && guesses.length) finishListening();
    else if (mode === "listening") resetListening();
  };
  recognition.onerror = (event) => {
    if (event.error === "aborted" || event.error === "no-speech") return;
    statusLine.textContent = "The microphone did not catch that. Tap to try again.";
  };
  recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const piece = event.results[i];
      const limit = piece.isFinal ? piece.length : 1;
      for (let alt = 0; alt < limit; alt += 1) noteGuess(piece[alt].transcript);
    }
  };
  try {
    recognition.start();
  } catch (error) {
    stopMeter();
    statusLine.textContent = "The microphone did not start. Tap to try again.";
  }
  maxTimer = setTimeout(() => finishListening(), 8000);
}

function noteGuess(text) {
  const cleaned = (text || "").trim();
  if (!cleaned) return;
  guesses.push(cleaned);
  caption.textContent = bestGuess();
  clearTimeout(silenceTimer);
  silenceTimer = setTimeout(() => finishListening(), 1200);
}

function finishListening() {
  if (listenSent) return;
  listenSent = true;
  clearTimeout(silenceTimer);
  clearTimeout(maxTimer);
  const heard = bestGuess();
  try { recognition.stop(); } catch (error) { /* already stopped */ }
  resetListening();
  if (heard) sendUtterance(heard);
}

function resetListening() {
  recognizing = false;
  stopMeter();
  if (mode === "listening") setMode("idle");
}

function bestGuess() {
  if (!guesses.length) return "";
  return guesses.slice().sort((left, right) => right.trim().length - left.trim().length)[0];
}

async function sendUtterance(raw) {
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
      statusLine.textContent = body.error || "The request failed.";
      setMode("idle");
      return;
    }
    if (body.speaker) speaker = body.speaker;
    appendLine("Family Dose Check", body.speech, "agent");
    await speak(body.speech);
  } catch (error) {
    statusLine.textContent = "The agent could not reach the server.";
    setMode("idle");
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

async function startMeter() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
  try {
    meterStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioContext = audioContext || new AudioContext();
    if (audioContext.state === "suspended") await audioContext.resume();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    audioContext.createMediaStreamSource(meterStream).connect(analyser);
  } catch (error) {
    analyser = null;
  }
}

function stopMeter() {
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
