const prompts = {
  older_adult: [
    "What's due now?",
    "I took the morning one",
    "What medicines does Raj take?",
    "Raj needs to take dopamine at 8 AM on Monday and Friday",
    "Switch to caregiver mode",
  ],
  caregiver: [
    "How is Raj doing?",
    "How did today go?",
    "Remove dopamine from Raj",
    "Clear today's log",
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
const peopleList = document.querySelector("#people");
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
const addTimeButton = document.querySelector("#add-time");
const medDialog = document.querySelector("#med-dialog");
const personDialog = document.querySelector("#person-dialog");
const detailDialog = document.querySelector("#detail-dialog");
let editing = null;
let currentPerson = "";
let latest = { people: [], schedules: [] };

DAY_LABELS.forEach((label, index) => {
  const box = document.createElement("label");
  box.className = "day-pick";
  box.innerHTML = `<input type="checkbox" value="${index}" checked /><span>${label}</span>`;
  dayPicks.append(box);
});

document.querySelectorAll("dialog [data-close]").forEach((button) => {
  button.addEventListener("click", () => button.closest("dialog").close());
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
  if (editing === null) {
    const drop = document.createElement("button");
    drop.type = "button";
    drop.className = "btn ghost small";
    drop.textContent = "×";
    drop.setAttribute("aria-label", "Remove this time");
    drop.addEventListener("click", () => { if (timeRows.children.length > 1) row.remove(); });
    row.append(drop);
  }
  timeRows.append(row);
}

function openMedicineForm(item) {
  editing = item ? item.schedule_id : null;
  scheduleForm.reset();
  formError.textContent = "";
  timeRows.replaceChildren();
  addTimeRow(item ? item.time_local : "08:00");
  addTimeButton.hidden = Boolean(item);
  setDays(item ? item.days : [0, 1, 2, 3, 4, 5, 6]);
  scheduleForm.dose_label.value = item ? item.dose_label : "";
  document.querySelector("#med-title").textContent = item
    ? `Edit ${currentPerson}'s medicine`
    : `Add medicine for ${currentPerson}`;
  submitButton.textContent = item ? "Save changes" : "Add medicine";
  detailDialog.close();
  medDialog.showModal();
  scheduleForm.dose_label.focus();
}

function closeMedicineForm() {
  medDialog.close();
  openDetail(currentPerson);
}

addTimeButton.addEventListener("click", () => addTimeRow("20:00"));
document.querySelector("#schedule-cancel").addEventListener("click", closeMedicineForm);
medDialog.addEventListener("cancel", (event) => { event.preventDefault(); closeMedicineForm(); });
document.querySelectorAll("[data-days]").forEach((button) => {
  button.addEventListener("click", () => setDays(button.dataset.days.split(",").map(Number)));
});

scheduleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.textContent = "";
  const days = pickedDays();
  if (!days.length) {
    formError.textContent = "Pick at least one day.";
    return;
  }
  const times = [...new Set([...timeRows.querySelectorAll("input")].map((input) => input.value).filter(Boolean))];
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
        body: JSON.stringify({ person_name: currentPerson, dose_label, time_local, days }),
      });
      if (!response.ok) { failure = (await response.json()).error || "Could not add that dose."; break; }
    }
  }
  if (failure) {
    formError.textContent = failure;
    return;
  }
  await refreshBoard();
  closeMedicineForm();
});

document.querySelector("#add-person").addEventListener("click", () => {
  document.querySelector("#person-form").reset();
  document.querySelector("#person-error").textContent = "";
  personDialog.showModal();
  document.querySelector("#person-form").name.focus();
});

document.querySelector("#person-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = event.target.name.value;
  const response = await fetch("/api/people", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const body = await response.json();
  if (!response.ok) {
    document.querySelector("#person-error").textContent = body.speech || "Could not add that person.";
    return;
  }
  personDialog.close();
  await refreshBoard();
  openDetail(body.person_name);
});

function openDetail(name) {
  currentPerson = name;
  const meds = latest.schedules.filter((item) => item.person_name.toLowerCase() === name.toLowerCase());
  document.querySelector("#detail-name").textContent = name;
  const avatar = document.querySelector("#detail-avatar");
  avatar.textContent = name.slice(0, 1).toUpperCase();
  avatar.className = `avatar large ${avatarClass(name)}`;
  document.querySelector("#detail-sub").textContent = meds.length
    ? `${meds.length} scheduled ${meds.length === 1 ? "dose" : "doses"}`
    : "No medicine yet. Add the first one.";
  const list = document.querySelector("#detail-meds");
  list.replaceChildren();
  meds.forEach((dose) => {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.innerHTML = `<strong>${escapeHtml(dose.dose_label)} · ${escapeHtml(dose.time_spoken)}</strong><span class="meta">${escapeHtml(dose.days_spoken)}</span>`;
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "btn ghost small";
    edit.textContent = "Edit";
    edit.addEventListener("click", () => openMedicineForm(dose));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn ghost small danger";
    remove.textContent = "Remove";
    remove.addEventListener("click", async () => {
      await fetch(`/api/schedules/${dose.schedule_id}`, { method: "DELETE" });
      await refreshBoard();
      openDetail(name);
    });
    const actions = document.createElement("span");
    actions.className = "row-actions";
    actions.append(edit, remove);
    item.append(text, actions);
    list.append(item);
  });
  if (!detailDialog.open) detailDialog.showModal();
}

document.querySelector("#detail-add").addEventListener("click", () => openMedicineForm(null));
document.querySelector("#detail-remove").addEventListener("click", async () => {
  if (!confirm(`Remove ${currentPerson} and all of their medicines?`)) return;
  await fetch(`/api/people/${encodeURIComponent(currentPerson)}`, { method: "DELETE" });
  detailDialog.close();
  await refreshBoard();
});

document.querySelector("#talk-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendUtterance(utteranceInput.value);
});

micButton.addEventListener("click", toggleMic);
renderPrompts();
appendBubble("Family Dose Check", "Hi! Ask what's due, say a dose was taken, or manage the household by voice. Use + Add person on the left to set someone up.", "assistant");
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
  latest = { people: board.people || [], schedules: board.schedules || [] };
  renderPeople();
  renderDoses(board.doses);
  renderAlerts(board.alerts);
}

function avatarClass(name) {
  let sum = 0;
  for (const char of name) sum += char.charCodeAt(0);
  return `c${(sum % 5) + 1}`;
}

function renderPeople() {
  peopleList.replaceChildren();
  if (!latest.people.length) {
    const none = document.createElement("li");
    none.className = "empty";
    none.textContent = "No one yet. Add a person to begin.";
    peopleList.append(none);
    return;
  }
  latest.people.forEach((name) => {
    const count = latest.schedules.filter((item) => item.person_name.toLowerCase() === name.toLowerCase()).length;
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "person";
    button.innerHTML = `<span class="avatar ${avatarClass(name)}">${escapeHtml(name.slice(0, 1).toUpperCase())}</span>`
      + `<span><strong>${escapeHtml(name)}</strong><span class="meta">${count ? `${count} ${count === 1 ? "dose" : "doses"} scheduled` : "No medicine yet"}</span></span>`;
    button.addEventListener("click", () => openDetail(name));
    item.append(button);
    peopleList.append(item);
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
  item.className = "empty";
  item.textContent = text;
  return item;
}

function tick() {
  clock.textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

const listener = new AutoListener({
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

