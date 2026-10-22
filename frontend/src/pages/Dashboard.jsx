import { useCallback, useRef, useState, useEffect } from "react";
import { api } from "../api";
import { speakAloud, stopSpeaking } from "../lib/speak";
import { useVoice } from "../hooks/useVoice";
import { useReminders } from "../hooks/useReminders";
import ReminderBanner from "../components/ReminderBanner";
import Sidebar from "../components/Sidebar";
import ChatPanel from "../components/ChatPanel";
import TodayPanel from "../components/TodayPanel";
import AddPersonDialog from "../components/AddPersonDialog";
import PersonDialog from "../components/PersonDialog";
import MedicineDialog from "../components/MedicineDialog";
import "../styles/dashboard.css";

const WELCOME = {
  id: 0,
  who: "Pillow",
  kind: "assistant",
  text: "Hi! Press Speak or type to ask what's due, or to say a dose was taken.",
};

const EMPTY_BOARD = { doses: [], alerts: [], people: [], schedules: [] };

export default function Dashboard({ session }) {
  const [board, setBoard] = useState(EMPTY_BOARD);
  const [speaker, setSpeaker] = useState("older_adult");
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [speakReplies, setSpeakReplies] = useState(true);
  const [dialog, setDialog] = useState({ kind: null, person: "", editing: null });
  const [reminder, setReminder] = useState("");
  const nextId = useRef(1);
  const speakRepliesRef = useRef(true);
  const listeningRef = useRef(false);

  const refresh = useCallback(async () => {
    const { ok, body } = await api.today();
    if (ok) setBoard({ doses: body.doses, alerts: body.alerts, people: body.people || [], schedules: body.schedules || [] });
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { speakRepliesRef.current = speakReplies; }, [speakReplies]);

  const checkReminders = useReminders((item) => {
    setReminder(item.speech);
    if (speakRepliesRef.current && !listeningRef.current) speakAloud(item.speech);
    setTimeout(() => setReminder((current) => (current === item.speech ? "" : current)), 20000);
  });
  useEffect(() => { checkReminders(); }, [board, checkReminders]);

  const addMessage = (message) => setMessages((current) => [...current, { id: nextId.current++, ...message }]);

  const send = useCallback(async (raw) => {
    if (busy) return;
    voice?.cancel();
    const utterance = raw.trim();
    setError("");
    setStatus("");
    if (!utterance) { setError("Say or type a sentence."); return; }
    addMessage({ who: speaker === "caregiver" ? "Caregiver" : "Older adult", kind: "user", text: utterance });
    setInput("");
    setBusy(true);
    try {
      const { ok, body } = await api.talk(utterance, speaker);
      if (!ok) { setError(body.error || "The request failed."); return; }
      if (body.speaker) setSpeaker(body.speaker);
      const trace = body.tool
        ? `MCP ${body.tool} · ${body.transport}${body.protocol ? " · " + body.protocol : ""}`
        : body.speaker_changed ? `Speaker ${body.speaker}` : "No tool called";
      addMessage({ who: "Pillow", kind: "assistant", text: body.speech, trace });
      if (speakReplies && !listeningRef.current) speakAloud(body.speech);
      await refresh();
    } catch {
      setError("The simulator could not reach the server.");
    } finally {
      setBusy(false);
    }
  }, [busy, speaker, speakReplies, refresh]);

  const voice = useVoice({
    onState: (active) => { listeningRef.current = active; setListening(active); if (active) { setError(""); setStatus(""); } },
    onTranscript: (text) => setInput(text),
    onStatus: (text) => setStatus(text || ""),
    onUtterance: (text) => send(text),
    onError: (text) => { setStatus(""); setError(text); },
  });

  function toggleMic() {
    if (busy || !voice) return;
    if (voice.active) { voice.finish(); return; }
    stopSpeaking();
    voice.start();
  }

  const closeDialog = () => setDialog({ kind: null, person: "", editing: null });
  const openPerson = (name) => setDialog({ kind: "person", person: name, editing: null });

  async function addPerson(name) {
    const { ok, body } = await api.addPerson(name);
    if (!ok) return body.speech || "Could not add that person.";
    await refresh();
    openPerson(body.person_name);
    return "";
  }

  async function saveMedicine({ dose_label, times, days }) {
    const { editing, person } = dialog;
    if (editing) {
      const { ok, body } = await api.updateSchedule(editing.schedule_id, { dose_label, time_local: times[0], days });
      if (!ok) return body.error || "Could not save that change.";
    } else {
      for (const time_local of times) {
        const { ok, body } = await api.addSchedule({ person_name: person, dose_label, time_local, days });
        if (!ok) return body.error || "Could not add that dose.";
      }
    }
    await refresh();
    openPerson(person);
    return "";
  }

  async function removeMedicine(dose) {
    await api.removeSchedule(dose.schedule_id);
    await refresh();
  }

  async function removePerson(name) {
    if (!window.confirm(`Remove ${name} and all of their medicines?`)) return;
    await api.removePerson(name);
    closeDialog();
    await refresh();
  }

  const placeholder = listening ? status || "Starting microphone…" : status || "What's due now?";

  return (
    <div className="app">
      <Sidebar
        session={session}
        people={board.people}
        onAdd={() => setDialog({ kind: "add-person", person: "", editing: null })}
        onOpen={openPerson}
      />
      <main className="main">
        <ReminderBanner text={reminder} onClose={() => setReminder("")} />
        <ChatPanel
          speaker={speaker}
          onSpeaker={setSpeaker}
          messages={messages}
          input={input}
          onInput={setInput}
          onSend={send}
          busy={busy}
          listening={listening}
          onMic={toggleMic}
          speakReplies={speakReplies}
          onSpeakReplies={setSpeakReplies}
          error={error}
          placeholder={placeholder}
          onWarm={() => voice?.warm?.()}
        />
      </main>
      <TodayPanel doses={board.doses} alerts={board.alerts} />

      <AddPersonDialog open={dialog.kind === "add-person"} onClose={closeDialog} onAdd={addPerson} />
      <PersonDialog
        person={dialog.kind === "person" ? dialog.person : ""}
        schedules={board.schedules}
        onClose={closeDialog}
        onAddMedicine={() => setDialog({ kind: "medicine", person: dialog.person, editing: null })}
        onEdit={(dose) => setDialog({ kind: "medicine", person: dialog.person, editing: dose })}
        onRemoveMedicine={removeMedicine}
        onRemovePerson={removePerson}
      />
      <MedicineDialog
        open={dialog.kind === "medicine"}
        person={dialog.person}
        editing={dialog.editing}
        onClose={() => openPerson(dialog.person)}
        onSave={saveMedicine}
      />
    </div>
  );
}
