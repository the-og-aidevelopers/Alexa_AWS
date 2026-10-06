const prompts = {
  older_adult: [
    "What's due now?",
    "Register him as Raj",
    "Raj needs to take medicine at 8 AM and 8 PM",
    "Switch to caregiver mode",
  ],
  caregiver: [
    "Did Mom take her morning medicine?",
    "How did today go?",
    "Switch to older adult mode",
  ],
};

const speakerNames = {
  older_adult: "Older adult",
  caregiver: "Caregiver",
};

let speaker = "older_adult";
let recognizing = false;

const transcript = document.querySelector("#transcript");
const promptBox = document.querySelector("#prompts");
const scheduleList = document.querySelector("#schedule-list");
const doseBoard = document.querySelector("#dose-board");
const alerts = document.querySelector("#alerts");
const formError = document.querySelector("#form-error");
const talkError = document.querySelector("#talk-error");
const utteranceInput = document.querySelector("#utterance");
const sendButton = document.querySelector("#send");
const micButton = document.querySelector("#mic");
const transport = document.querySelector("#transport");
const clock = document.querySelector("#clock");

document.querySelectorAll(".role").forEach((button) => {
  button.addEventListener("click", () => setSpeaker(button.dataset.speaker));
});

document.querySelector("#schedule-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.textContent = "";
  const data = Object.fromEntries(new FormData(event.target));
  const response = await fetch("/api/schedules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const body = await response.json();
  if (!response.ok) {
    formError.textContent = body.error || "Could not add that dose.";
    return;
  }
  event.target.reset();
  event.target.time_local.value = "08:00";
  await refreshBoard();
});

document.querySelector("#talk-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendUtterance(utteranceInput.value);
});

document.querySelector("#reset-day").addEventListener("click", async () => {
  await fetch("/api/logs/reset", { method: "POST" });
  await refreshBoard();
});

micButton.addEventListener("click", toggleMic);
renderPrompts();
refreshBoard();
tick();
setInterval(tick, 1000);

function renderPrompts() {
  promptBox.replaceChildren();
  prompts[speaker].forEach((text) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "prompt";
    button.textContent = text;
    button.addEventListener("click", () => {
      utteranceInput.value = text;
      sendUtterance(text);
    });
    promptBox.append(button);
  });
}

function setSpeaker(next) {
  if (!speakerNames[next]) return;
  speaker = next;
  document.querySelectorAll(".role").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.speaker === speaker);
  });
  renderPrompts();
}

async function sendUtterance(raw) {
  if (sendButton.disabled) return;
  listener.cancel();
  const utterance = raw.trim();
  talkError.textContent = "";
  if (!utterance) {
    talkError.textContent = "Say or type a sentence.";
    return;
  }
  appendBubble(speakerNames[speaker], utterance, "user");
  utteranceInput.value = "";
  sendButton.disabled = true;
  try {
    const response = await fetch("/api/talk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ utterance, speaker }),
    });
    const body = await response.json();
    if (!response.ok) {
      talkError.textContent = body.error || "The request failed.";
      return;
    }
    if (body.speaker) setSpeaker(body.speaker);
    const trace = body.tool
      ? `MCP ${body.tool} · ${body.transport}${body.protocol ? " · " + body.protocol : ""}`
      : body.speaker_changed
        ? `Speaker ${body.speaker}`
        : "No tool called";
    appendBubble("Family Dose Check", body.speech, "assistant", trace);
    if (body.protocol) {
      transport.textContent = `${body.transport} · ${body.protocol}`;
    }
    if (document.querySelector("#speak-replies").checked) {
      speak(body.speech);
    }
    await refreshBoard();
  } catch (error) {
    talkError.textContent = "The simulator could not reach the server.";
  } finally {
    sendButton.disabled = false;
    utteranceInput.focus();
  }
}

function appendBubble(who, text, kind, trace) {
  const item = document.createElement("li");
  item.className = `bubble ${kind}`;
  const label = document.createElement("p");
  label.className = "who";
  label.textContent = who;
  const message = document.createElement("p");
  message.textContent = text;
  item.append(label, message);
  if (trace) {
    const line = document.createElement("p");
    line.className = "trace";
    line.textContent = trace;
    item.append(line);
  }
  transcript.append(item);
  transcript.scrollTop = transcript.scrollHeight;
}

async function refreshBoard() {
  const response = await fetch("/api/today");
  const board = await response.json();
  renderSchedule(board.doses, board.people || []);
  renderDoses(board.doses);
  renderAlerts(board.alerts);
}

function renderSchedule(doses, people) {
  scheduleList.replaceChildren();
  const named = new Set(doses.map((dose) => dose.person_name.toLowerCase()));
  people
    .filter((name) => !named.has(name.toLowerCase()))
    .forEach((name) => {
      const item = document.createElement("li");
      item.innerHTML = `<strong>${escapeHtml(name)}</strong><span class="meta">Registered, no medicine yet</span>`;
      scheduleList.append(item);
    });
  if (!doses.length && !scheduleList.children.length) {
    scheduleList.append(noteItem("No doses yet."));
    return;
  }
  doses.forEach((dose) => {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.innerHTML = `<strong>${escapeHtml(dose.person_name)}</strong><span class="meta">${escapeHtml(dose.dose_label)} · ${escapeHtml(dose.time_spoken)}</span>`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "ghost";
    remove.textContent = "Remove";
    remove.addEventListener("click", async () => {
      await fetch(`/api/schedules/${dose.schedule_id}`, { method: "DELETE" });
      await refreshBoard();
    });
    item.append(text, remove);
    scheduleList.append(item);
  });
}

function renderDoses(doses) {
  doseBoard.replaceChildren();
  if (!doses.length) {
    doseBoard.append(noteItem("Add a dose to start the day."));
    return;
  }
  doses.forEach((dose) => {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.innerHTML = `<strong>${escapeHtml(dose.time_spoken)} ${escapeHtml(dose.dose_label)}</strong><span class="meta">${escapeHtml(dose.person_name)}</span>`;
    const state = document.createElement("span");
    state.className = `state ${dose.state}`;
    state.textContent = dose.state;
    item.append(text, state);
    doseBoard.append(item);
  });
}

function renderAlerts(items) {
  alerts.classList.toggle("is-clear", items.length === 0);
  alerts.replaceChildren();
  if (!items.length) {
    const line = document.createElement("p");
    line.textContent = "No family alerts.";
    alerts.append(line);
    return;
  }
  items.forEach((dose) => {
    const line = document.createElement("p");
    const late = dose.minutes_late >= 60
      ? `${Math.floor(dose.minutes_late / 60)} hours past the grace window`
      : `${dose.minutes_late} minutes past the grace window`;
    line.textContent = `${dose.person_name}'s ${dose.time_spoken} ${dose.dose_label} is still open, ${late}.`;
    alerts.append(line);
  });
}

function noteItem(text) {
  const item = document.createElement("li");
  item.textContent = text;
  return item;
}

function tick() {
  clock.textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

const listener = new SpeechListener({
  onState(active) {
    recognizing = active;
    micButton.setAttribute("aria-pressed", String(active));
    micButton.textContent = active ? "Done" : "Mic";
    utteranceInput.placeholder = active ? "Listening… pause when you finish" : "What's due now?";
    if (active) talkError.textContent = "";
  },
  onTranscript(text) { utteranceInput.value = text; },
  onUtterance: sendUtterance,
  onError(text) { talkError.textContent = text; },
});

function toggleMic() {
  if (sendButton.disabled) return;
  if (listener.active) { listener.finish(); return; }
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  listener.start();
}

window.addEventListener("pagehide", () => listener.cancel());

function speak(text) {
  if (!window.speechSynthesis || recognizing) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 0.95;
  window.speechSynthesis.speak(utterance);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

