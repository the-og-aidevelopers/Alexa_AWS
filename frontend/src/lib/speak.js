export function speakAloud(text, { onStart, onEnd } = {}) {
  const synth = window.speechSynthesis;
  if (!synth) {
    onEnd?.();
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    synth.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95;
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      onEnd?.();
      resolve();
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    const timer = setTimeout(finish, Math.min(20000, Math.max(1600, text.length * 75)));
    onStart?.();
    synth.speak(utterance);
  });
}

export function stopSpeaking() {
  window.speechSynthesis?.cancel();
}
