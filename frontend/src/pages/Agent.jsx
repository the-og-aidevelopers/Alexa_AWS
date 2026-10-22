import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { speakAloud, stopSpeaking } from "../lib/speak";
import { useVoice } from "../hooks/useVoice";
import { useMeter } from "../hooks/useMeter";
import { useReminders } from "../hooks/useReminders";
import Orb from "../components/Orb";
import "../styles/agent.css";

const LABELS = {
  idle: "Tap the circle to talk",
  listening: "Listening",
  thinking: "One moment",
  speaking: "Speaking",
};

export default function Agent({ session }) {
  const [mode, setMode] = useState("idle");
  const [status, setStatus] = useState("");
  const [caption, setCaption] = useState("");
  const [lines, setLines] = useState([]);
  const speaker = useRef("older_adult");
  const modeRef = useRef("idle");
  const listeningRef = useRef(false);
  const nextId = useRef(1);
  const end = useRef(null);

  const changeMode = useCallback((next) => {
    modeRef.current = next;
    setMode(next);
    setStatus("");
  }, []);

  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [lines]);

  const sendUtterance = useCallback(async (raw) => {
    if (modeRef.current === "thinking") return;
    voice?.cancel();
    const utterance = raw.trim();
    if (!utterance) return;
    setCaption("");
    setLines((current) => [...current, { id: nextId.current++, who: "You", kind: "you", text: utterance }]);
    changeMode("thinking");
    try {
      const { ok, body } = await api.talk(utterance, speaker.current);
      if (!ok) { changeMode("idle"); setStatus(body.error || "The request failed."); return; }
      if (body.speaker) speaker.current = body.speaker;
      setLines((current) => [...current, { id: nextId.current++, who: "Family Dose Check", kind: "agent", text: body.speech }]);
      if (listeningRef.current) { changeMode("idle"); return; }
      await speakAloud(body.speech, {
        onStart: () => changeMode("speaking"),
        onEnd: () => { if (modeRef.current === "speaking") changeMode("idle"); },
      });
      if (modeRef.current === "thinking") changeMode("idle");
    } catch {
      changeMode("idle");
      setStatus("The agent could not reach the server.");
    }
  }, [changeMode]);

  const voice = useVoice({
    onState: (active) => {
      listeningRef.current = active;
      if (active) changeMode("listening");
      else if (modeRef.current === "listening") changeMode("idle");
    },
    onTranscript: (text) => setCaption(text),
    onStatus: (text) => { if (text) setStatus(text); },
    onUtterance: sendUtterance,
    onError: (text) => { setStatus(text); },
  });

  const meter = useMeter(mode === "listening");

  useReminders((item) => {
    setLines((current) => [...current, { id: nextId.current++, who: "Reminder", kind: "agent", text: item.speech }]);
    if (modeRef.current === "idle" && !listeningRef.current) {
      speakAloud(item.speech, { onStart: () => changeMode("speaking"), onEnd: () => { if (modeRef.current === "speaking") changeMode("idle"); } });
    }
  });

  useEffect(() => {
    const say = (event) => { if (typeof event.detail === "string") sendUtterance(event.detail); };
    document.addEventListener("dose-say", say);
    return () => document.removeEventListener("dose-say", say);
  }, [sendUtterance]);

  function toggleMic() {
    if (!voice || modeRef.current === "thinking") return;
    if (voice.active) { voice.finish(); return; }
    stopSpeaking();
    voice.start();
  }

  return (
    <div className="agent-page">
      <div className="agent-account">
        <a className="dev-link" href="/">Caregiver dashboard</a>
        <span>{session.identity?.household_name}</span>
        {(session.provider === "local" || session.provider === "cognito") && <button type="button" onClick={session.signOut}>Sign out</button>}
      </div>
      <main>
        <p className="status" role="status">{status || LABELS[mode]}</p>
        <Orb mode={mode} analyser={meter} onClick={toggleMic} onWarm={() => voice?.warm?.()} />
        <p className="caption" aria-live="polite">{caption}</p>
        <ol className="transcript" aria-live="polite">
          {lines.map((line) => (
            <li key={line.id} className={`line ${line.kind}`}>
              <p className="who">{line.who}</p>
              <p>{line.text}</p>
            </li>
          ))}
          <li ref={end} aria-hidden="true" />
        </ol>
      </main>
    </div>
  );
}
