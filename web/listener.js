(function (root) {
  "use strict";

  // Each event contains the complete current session, not just new words.
  function transcriptFrom(results, finalOnly = false) {
    return Array.from(results)
      .filter((result) => !finalOnly || result.isFinal)
      .map((result) => (result[0]?.transcript || "").trim())
      .filter(Boolean)
      .join(" ");
  }

  class SpeechListener {
    constructor({ onState, onTranscript, onUtterance, onError }) {
      this.onState = onState;
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
        this.onError("This browser has no speech recognition. Type on the development page instead.");
        return;
      }
      const session = { recognition: null, finalText: "", stopping: false, timers: {} };
      this.session = session;
      this.onTranscript("");
      this.onState(true);
      try {
        const recognition = new Recognition();
        session.recognition = recognition;
        const language = root.navigator?.language || "en-GB";
        recognition.lang = language.startsWith("en") ? language : "en-GB";
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;
        recognition.continuous = true;
        recognition.onresult = (event) => {
          if (this.session !== session) return;
          session.finalText = transcriptFrom(event.results, true);
          const preview = transcriptFrom(event.results);
          this.onTranscript(preview);
          clearTimeout(session.timers.silence);
          if (preview && !session.stopping) {
            session.timers.silence = setTimeout(() => this.finish(), 1200);
          }
        };
        recognition.onend = () => this.complete(session);
        recognition.onerror = (event) => {
          if (this.session !== session) return;
          this.cancel();
          if (event.error === "aborted") return;
          this.onError(event.error === "no-speech"
            ? "Didn't catch speech. Move closer to the mic and try again."
            : "The microphone could not recognize speech. Check permission and try again.");
        };
        // Lock the session before start() so rapid taps cannot create two listeners.
        recognition.start();
        if (this.session === session) {
          session.timers.max = setTimeout(() => this.finish(), 20000);
        }
      } catch (error) {
        this.cancel();
        this.onError("The microphone did not start. Check permission and try again.");
      }
    }

    finish() {
      const session = this.session;
      if (!session || session.stopping) return;
      session.stopping = true;
      clearTimeout(session.timers.silence);
      clearTimeout(session.timers.max);
      // stop() can deliver a final result before end; don't submit the interim guess.
      session.timers.drain = setTimeout(() => {
        this.complete(session);
        try { session.recognition.abort(); } catch (error) { /* already ended */ }
      }, 1500);
      try { session.recognition.stop(); }
      catch (error) { this.complete(session); }
    }

    complete(session) {
      if (this.session !== session) return;
      this.clear(session);
      if (session.finalText) this.onUtterance(session.finalText);
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
  if (typeof module !== "undefined") module.exports = { SpeechListener, transcriptFrom };
})(typeof window !== "undefined" ? window : globalThis);
