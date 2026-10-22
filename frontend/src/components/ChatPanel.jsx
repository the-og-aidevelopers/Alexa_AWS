import { useEffect, useRef } from "react";

export const PROMPTS = {
  older_adult: [
    "What's due now?",
    "I took the morning one",
    "Switch to caregiver mode",
  ],
  caregiver: [
    "How did today go?",
    "Clear today's log",
    "Switch to older adult mode",
  ],
};

const SPEAKERS = { older_adult: "Older adult", caregiver: "Caregiver" };

export default function ChatPanel({
  speaker, onSpeaker, messages, input, onInput, onSend, busy, listening, onMic,
  speakReplies, onSpeakReplies, error, placeholder, onWarm,
}) {
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [messages]);

  return (
    <section className="chat" aria-labelledby="talk-heading">
      <div className="chat-head">
        <h2 id="talk-heading">How can I help?</h2>
        <div className="roles" role="group" aria-label="Who is speaking">
          {Object.entries(SPEAKERS).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`role${speaker === key ? " is-active" : ""}`}
              onClick={() => onSpeaker(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="prompts">
        {PROMPTS[speaker].map((text) => (
          <button key={text} type="button" className="prompt" onClick={() => onSend(text)}>{text}</button>
        ))}
      </div>
      <ol className="transcript" aria-live="polite">
        {messages.map((message) => (
          <li key={message.id} className={`bubble ${message.kind}`} title={message.trace || undefined}>
            <p>{message.text}</p>
          </li>
        ))}
        <li ref={end} aria-hidden="true" />
      </ol>
      {error && <p className="form-error" role="status">{error}</p>}
      <form
        className="composer"
        onSubmit={(event) => { event.preventDefault(); onSend(input); }}
      >
        <label className="sr-only" htmlFor="utterance">What to say</label>
        <input
          id="utterance"
          autoComplete="off"
          value={input}
          onChange={(event) => onInput(event.target.value)}
          placeholder={placeholder}
        />
        <button type="button" className="btn ghost" aria-pressed={listening} onPointerEnter={onWarm} onFocus={onWarm} aria-label={listening ? "Done speaking" : "Speak"} onClick={onMic}>
          {listening ? "Done" : "Speak"}
        </button>
        <button type="submit" className="btn" disabled={busy}>Ask</button>
      </form>
      <label className="speak-toggle">
        <input type="checkbox" checked={speakReplies} onChange={(event) => onSpeakReplies(event.target.checked)} />
        Read answers aloud
      </label>
    </section>
  );
}
