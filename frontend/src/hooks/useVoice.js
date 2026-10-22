import { useEffect, useRef } from "react";

// One microphone listener per page. It uses the local Whisper recorder when the server offers it
// and the browser's speech engine otherwise (see public/recorder.js and public/listener.js).
export function useVoice(handlers) {
  const latest = useRef(handlers);
  latest.current = handlers;
  const listener = useRef(null);

  if (listener.current === null) {
    const Listener = window.AutoListener;
    listener.current = Listener
      ? new Listener({
          onState: (active) => latest.current.onState?.(active),
          onTranscript: (text) => latest.current.onTranscript?.(text),
          onStatus: (text) => latest.current.onStatus?.(text),
          onUtterance: (text) => latest.current.onUtterance?.(text),
          onError: (text) => latest.current.onError?.(text),
        })
      : null;
  }

  useEffect(() => {
    const voice = listener.current;
    const stop = () => voice?.cancel();
    window.addEventListener("pagehide", stop);
    return () => {
      window.removeEventListener("pagehide", stop);
      stop();
    };
  }, []);

  return listener.current;
}
