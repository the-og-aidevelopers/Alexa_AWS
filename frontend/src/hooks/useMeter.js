import { useEffect, useState } from "react";

function release(stream) {
  if (window.MicPool) window.MicPool.release();
  else stream.getTracks().forEach((track) => track.stop());
}

// A microphone level meter for the orb, separate from the recognizer so it can run alongside it.
export function useMeter(active) {
  const [analyser, setAnalyser] = useState(null);

  useEffect(() => {
    if (!active || !navigator.mediaDevices?.getUserMedia) return undefined;
    let cancelled = false;
    let stream = null;
    let context = null;
    (async () => {
      try {
        stream = window.MicPool
          ? await window.MicPool.acquire()
          : await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          });
        if (cancelled) { release(stream); return; }
        context = new AudioContext();
        if (context.state === "suspended") await context.resume();
        const node = context.createAnalyser();
        node.fftSize = 256;
        context.createMediaStreamSource(stream).connect(node);
        if (!cancelled) setAnalyser(node);
      } catch {
        setAnalyser(null);
      }
    })();
    return () => {
      cancelled = true;
      if (stream) release(stream);
      context?.close?.().catch?.(() => {});
      setAnalyser(null);
    };
  }, [active]);

  return analyser;
}
