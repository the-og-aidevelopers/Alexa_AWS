(function (root) {
  "use strict";

  // The browser's own speech engine, left running in one continuous session so no
  // audio is lost between restarts. A pause of SILENCE_MS sends the sentence.
  const SILENCE_MS = 1800;

  function guessScore(text) {
    const folded = text.toLowerCase();
    let score = 0;
    if (/\b(add|register|take|took|takes|need|needs|medicine|due|skip|skipped|dose|dopamine)\b/.test(folded)) score += 3;
    if (/\b(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?|morning|evening|afternoon|night)\b/.test(folded)) score += 2;
    if (/\b(address|docomo)\b/.test(folded)) score -= 3;
    return score;
  }

  function bestAlternative(result) {
    let chosen = "";
    let best = -1;
    const limit = result.isFinal ? result.length : 1;
    for (let index = 0; index < limit; index += 1) {
      const text = (result[index]?.transcript || "").trim();
      if (!text) continue;
      const score = guessScore(text);
      if (!chosen || score > best) {
        chosen = text;
        best = score;
      }
    }
    return chosen;
  }

  function transcriptFrom(results, finalOnly = false) {
    return Array.from(results)
      .filter((result) => !finalOnly || result.isFinal)
      .map((result) => bestAlternative(result))
      .filter(Boolean)
      .join(" ");
  }

  class SpeechListener {
    constructor({ onState, onTranscript, onStatus, onUtterance, onError }) {
      this.onState = onState;
      this.onStatus = onStatus || (() => {});
      this.onTranscript = onTranscript;
      this.onUtterance = onUtterance;
      this.onError = onError;
      this.session = null;
    }

    get active() { return this.session !== null; }

    start() {
      if (this.active) return;
      const Recognition = root.SpeechRecognition || root.webkitSpeechRecognition;
      if (!Recognition) {
        this.onError("This browser has no speech recognition. Type the sentence instead.");
        return;
      }
      const session = {
        recognition: null,
        finalText: "",
        latest: "",
        stopping: false,
        timers: {},
      };
      this.session = session;
      this.onTranscript("");
      this.onState(true);
      this.onStatus("Starting microphone…");
      try {
        this.openRecognition(session);
        if (this.session === session) {
          session.timers.max = setTimeout(() => this.finish(), 20000);
        }
      } catch (error) {
        this.cancel();
        this.onError("The microphone did not start. Check permission and try again.");
      }
    }

    openRecognition(session) {
      const Recognition = root.SpeechRecognition || root.webkitSpeechRecognition;
      const recognition = new Recognition();
      session.recognition = recognition;
      const language = root.navigator?.language || "en-GB";
      recognition.lang = language.startsWith("en") ? language : "en-GB";
      recognition.interimResults = true;
      recognition.maxAlternatives = 5;
      recognition.continuous = true;
      recognition.onstart = () => {
        if (this.session === session) this.onStatus("Listening… pause when you finish");
      };
      recognition.onresult = (event) => {
        if (this.session !== session) return;
        session.finalText = transcriptFrom(event.results, true);
        session.latest = transcriptFrom(event.results);
        this.onTranscript(session.latest);
        if (session.stopping) return;
        clearTimeout(session.timers.silence);
        if (session.latest) {
          session.timers.silence = setTimeout(() => this.finish(), SILENCE_MS);
        }
      };
      recognition.onend = () => {
        if (this.session !== session) return;
        this.complete(session);
      };
      recognition.onerror = (event) => {
        if (this.session !== session) return;
        if (event.error === "aborted") return;
        this.cancel();
        if (event.error === "no-speech") {
          this.onError("Didn't catch speech. Move closer to the mic and try again.");
          return;
        }
        this.onError("The microphone could not recognize speech. Check permission and try again.");
      };
      recognition.start();
    }

    finish() {
      const session = this.session;
      if (!session || session.stopping) return;
      session.stopping = true;
      clearTimeout(session.timers.silence);
      clearTimeout(session.timers.max);
      session.timers.drain = setTimeout(() => {
        this.complete(session);
        try { session.recognition.abort(); } catch (error) { /* already ended */ }
      }, 1500);
      try { session.recognition.stop(); }
      catch (error) { this.complete(session); }
    }

    complete(session) {
      if (this.session !== session) return;
      const heard = session.finalText;
      this.clear(session);
      if (heard) this.onUtterance(heard);
      else this.onError("Didn't catch a complete sentence. Please try again or type it.");
    }

    cancel() {
      const session = this.session;
      if (!session) return;
      this.clear(session);
      try { session.recognition?.abort(); } catch (error) { /* already ended */ }
    }

    clear(session) {
      Object.values(session.timers).forEach(clearTimeout);
      this.session = null;
      this.onState(false);
    }
  }

  root.SpeechListener = SpeechListener;
  if (typeof module !== "undefined") module.exports = { SpeechListener, transcriptFrom, guessScore };
})(typeof window !== "undefined" ? window : globalThis);
