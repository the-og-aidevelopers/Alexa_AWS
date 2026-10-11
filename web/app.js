const prompts = {
  older_adult: [
    "What's due now?",
    "Register him as Raj",
    "Raj needs to take dopamine at 8 AM on Monday and Friday",
    "What medicines does Raj take?",
    "Switch to caregiver mode",
  ],
  caregiver: [
    "Did Mom take her morning medicine?",
    "How is Raj doing?",
    "How did today go?",
    "Remove dopamine from Raj",
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

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const scheduleForm = document.querySelector("#schedule-form");
const timeRows = document.querySelector("#time-rows");
const dayPicks = document.querySelector("#day-picks");
const submitButton = document.querySelector("#schedule-submit");
const cancelButton = document.querySelector("#schedule-cancel");
const addTimeButton = document.querySelector("#add-time");
let editing = null;

DAY_LABELS.forEach((label, index) => {
  const box = document.createElement("label");
  box.className = "day-pick";
  box.innerHTML = `<input type="checkbox" value="${index}" checked /><span>${label}</span>`;
  dayPicks.append(box);
});

function setDays(days) {
  dayPicks.querySelectorAll("input").forEach((input) => {
    input.checked = days.includes(Number(input.value));
  });
}

function pickedDays() {
  return [...dayPicks.querySelectorAll("input:checked")].map((input) => Number(input.value));
}

function addTimeRow(value = "08:00") {
  const row = document.createElement("div");
  row.className = "time-row";
  const input = document.createElement("input");
  input.type = "time";
  input.required = true;
  input.value = value;
  row.append(input);
  if (!editing) {
    const drop = document.createElement("button");
    drop.type = "button";
    drop.className = "ghost";
    drop.textContent = "×";
    drop.setAttribute("aria-label", "Remove this time");
    drop.addEventListener("click", () => { if (timeRows.children.length > 1) row.remove(); });
    row.append(drop);
  }
  timeRows.append(row);
}

function resetForm() {
  editing = null;
  scheduleForm.reset();
  scheduleForm.person_name.readOnly = false;
  timeRows.replaceChildren();
  addTimeRow();
  addTimeButton.hidden = false;
  setDays([0, 1, 2, 3, 4, 5, 6]);
  submitButton.textContent = "Add medicine";
  cancelButton.hidden = true;
}

function startEdit(item) {
  editing = item.schedule_id;
  scheduleForm.person_name.value = item.person_name;
  scheduleForm.person_name.readOnly = true;
  scheduleForm.dose_label.value = item.dose_label;
  timeRows.replaceChildren();
  addTimeRow(item.time_local);
  addTimeButton.hidden = true;
  setDays(item.days);
  submitButton.textContent = "Save changes";
  cancelButton.hidden = false;
  scheduleForm.dose_label.focus();
}

addTimeButton.addEventListener("click", () => addTimeRow("20:00"));
cancelButton.addEventListener("click", resetForm);
document.querySelectorAll("[data-days]").forEach((button) => {
  button.addEventListener("click", () => setDays(button.dataset.days.split(",").map(Number)));
});
resetForm();

scheduleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.textContent = "";
  const days = pickedDays();
  if (!days.length) {
    formError.textContent = "Pick at least one day.";
    return;
  }
  const times = [...new Set([...timeRows.querySelectorAll("input")].map((input) => input.value).filter(Boolean))];
  const person_name = scheduleForm.person_name.value;
  const dose_label = scheduleForm.dose_label.value;
  let failure = "";
  if (editing !== null) {
    const response = await fetch(`/api/schedules/${editing}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dose_label, time_local: times[0], days }),
    });
    if (!response.ok) failure = (await response.json()).error || "Could not save that change.";
  } else {
    for (const time_local of times) {
      const response = await fetch("/api/schedules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ person_name, dose_label, time_local, days }),
      });
      if (!response.ok) { failure = (await response.json()).error || "Could not add that dose."; break; }
    }
  }
  if (failure) {
    formError.textContent = failure;
    return;
  }
  resetForm();
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
  renderSchedule(board.schedules || [], board.people || []);
  renderPeopleList(board.people || []);
  renderDoses(board.doses);
  renderAlerts(board.alerts);
}

function renderPeopleList(people) {
  const list = document.querySelector("#people-list");
  list.replaceChildren(...people.map((name) => {
    const option = document.createElement("option");
    option.value = name;
    return option;
  }));
}

function renderSchedule(schedules, people) {
  scheduleList.replaceChildren();
  const grouped = new Map();
  people.forEach((name) => grouped.set(name.toLowerCase(), { name, items: [] }));
  schedules.forEach((item) => {
    const key = item.person_name.toLowerCase();
    if (!grouped.has(key)) grouped.set(key, { name: item.person_name, items: [] });
    grouped.get(key).items.push(item);
  });
  if (!grouped.size) {
    scheduleList.append(noteItem("No people or medicines yet."));
    return;
  }
  grouped.forEach(({ name, items }) => {
    const head = document.createElement("li");
    head.className = "person-head";
    const title = document.createElement("strong");
    title.textContent = name;
    const dropPerson = document.createElement("button");
    dropPerson.type = "button";
    dropPerson.className = "ghost";
    dropPerson.textContent = "Remove person";
    dropPerson.addEventListener("click", async () => {
      if (!confirm(`Remove ${name} and all of their medicines?`)) return;
      await fetch(`/api/people/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (editing !== null) resetForm();
      await refreshBoard();
    });
    head.append(title, dropPerson);
    scheduleList.append(head);
    if (!items.length) scheduleList.append(noteItem("No medicine yet."));
    items.forEach((dose) => {
      const item = document.createElement("li");
      const text = document.createElement("span");
      text.innerHTML = `<strong>${escapeHtml(dose.dose_label)} · ${escapeHtml(dose.time_spoken)}</strong><span class="meta">${escapeHtml(dose.days_spoken)}</span>`;
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "ghost";
      edit.textContent = "Edit";
      edit.addEventListener("click", () => startEdit(dose));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "ghost";
      remove.textContent = "Remove";
      remove.addEventListener("click", async () => {
        await fetch(`/api/schedules/${dose.schedule_id}`, { method: "DELETE" });
        if (editing === dose.schedule_id) resetForm();
        await refreshBoard();
      });
      const actions = document.createElement("span");
      actions.className = "row-actions";
      actions.append(edit, remove);
      item.append(text, actions);
      scheduleList.append(item);
    });
  });
}

function renderDoses(doses) {
  doseBoard.replaceChildren();
  if (!doses.length) {
    doseBoard.append(noteItem("No doses scheduled for today."));
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
  onStatus(text) { if (text) utteranceInput.placeholder = text; },
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

