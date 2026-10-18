(function (root) {
  "use strict";

  // Records one phrase from the microphone and sends it to the server's local Whisper
  // model (POST /api/transcribe). Voice activity decides when the phrase has ended.
  const POLL_MS = 100;
  const SILENCE_MS = 1300;
  const NO_SPEECH_MS = 8000;
  const MAX_MS = 30000;

  function pickMime() {
    const Recorder = root.MediaRecorder;
    if (!Recorder || !Recorder.isTypeSupported) return "";
    return ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]
      .find((type) => Recorder.isTypeSupported(type)) || "";
  }

  class RecordingListener {
    constructor({ onState, onTranscript, onStatus, onUtterance, onError }) {
      this.onState = onState;
      this.onTranscript = onTranscript;
      this.onStatus = onStatus || (() => {});
      this.onUtterance = onUtterance;
      this.onError = onError;
      this.session = null;
    }

    get active() { return this.session !== null; }

    async start() {
      if (this.active) return;
      if (!root.navigator?.mediaDevices?.getUserMedia || !root.MediaRecorder) {
        this.onError("This browser cannot record audio. Type the sentence instead.");
        return;
      }
      const session = { stream: null, recorder: null, chunks: [], timers: {}, discard: false, context: null };
      this.session = session;
      this.onTranscript("");
      this.onState(true);
      try {
        session.stream = await root.navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
        });
        if (this.session !== session) { this.release(session); return; }
        const mimeType = pickMime();
        session.recorder = new root.MediaRecorder(session.stream, mimeType ? { mimeType } : undefined);
        session.mime = session.recorder.mimeType || mimeType || "audio/webm";
        session.recorder.ondataavailable = (event) => { if (event.data?.size) session.chunks.push(event.data); };
        session.recorder.onstop = () => this.upload(session);
        session.recorder.start();
        this.onStatus("Listening…");
        this.watch(session);
      } catch (error) {
        if (this.session === session) this.abort(session);
        this.onError("The microphone did not start. Check permission and try again.");
      }
    }

    watch(session) {
      const Context = root.AudioContext || root.webkitAudioContext;
      const started = Date.now();
      let heard = false;
      let lastVoice = started;
      let floor = null;
      let analyser = null;
      let samples = null;
      if (Context) {
        session.context = new Context();
        analyser = session.context.createAnalyser();
        analyser.fftSize = 1024;
        session.context.createMediaStreamSource(session.stream).connect(analyser);
        samples = new Float32Array(analyser.fftSize);
      }
      session.timers.poll = setInterval(() => {
        if (this.session !== session) return;
        const now = Date.now();
        if (analyser) {
          analyser.getFloatTimeDomainData(samples);
          let sum = 0;
          for (const value of samples) sum += value * value;
          const level = Math.sqrt(sum / samples.length);
          floor = Math.min(floor ?? level, level);
          // The quietest moment so far is the room noise; speech must clearly rise above it.
          if (level > Math.max(0.02, Math.min(floor * 3, 0.05))) { heard = true; lastVoice = now; }
        }
        if (heard && now - lastVoice > SILENCE_MS) this.finish();
        else if (!heard && analyser && now - started > NO_SPEECH_MS) {
          this.abort(session);
          this.onError("Didn't catch speech. Move closer to the mic and try again.");
        } else if (now - started > MAX_MS) this.finish();
      }, POLL_MS);
    }

    finish() {
      const session = this.session;
      if (!session || !session.recorder || session.recorder.state === "inactive") return;
      this.clearTimers(session);
      this.onState(false);
      this.onStatus("Transcribing…");
      session.stopped = true;
      try { session.recorder.stop(); } catch (error) { this.abort(session); }
    }

    async upload(session) {
      this.release(session);
      if (this.session === session) this.session = null;
      if (session.discard) return;
      const blob = new Blob(session.chunks, { type: session.mime });
      if (blob.size < 1000) {
        this.onError("Didn't catch a complete sentence. Please try again or type it.");
        return;
      }
      try {
        const response = await root.fetch("/api/transcribe", {
          method: "POST",
          headers: { "Content-Type": session.mime },
          body: blob,
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.error || "Transcription failed.");
        const text = (body.text || "").trim();
        if (!text) {
          this.onError("Didn't catch a complete sentence. Please try again or type it.");
          return;
        }
        this.onTranscript(text);
        this.onUtterance(text);
      } catch (error) {
        this.onError(error.message || "Transcription failed.");
      }
    }

    cancel() {
      const session = this.session;
      if (!session) return;
      this.abort(session);
    }

    abort(session) {
      session.discard = true;
      this.clearTimers(session);
      try { if (session.recorder && session.recorder.state !== "inactive") session.recorder.stop(); } catch (error) { /* ended */ }
      this.release(session);
      if (this.session === session) {
        this.session = null;
        this.onState(false);
      }
    }

    clearTimers(session) {
      clearInterval(session.timers.poll);
      session.timers.poll = null;
    }

    release(session) {
      this.clearTimers(session);
      session.stream?.getTracks().forEach((track) => track.stop());
      try { session.context?.close(); } catch (error) { /* closed */ }
      session.stream = null;
      session.context = null;
    }
  }

  // Uses the local Whisper model when the server reports it, else the browser's own engine.
  class AutoListener {
    constructor(handlers) {
      this.browser = new root.SpeechListener(handlers);
      this.recording = new RecordingListener(handlers);
      this.useServer = false;
      this.ready = root.fetch("/api/health", { cache: "no-store" })
        .then((response) => response.json())
        .then((body) => { this.useServer = Boolean(body?.capabilities?.transcribe); })
        .catch(() => { this.useServer = false; });
    }

    get active() { return this.browser.active || this.recording.active; }

    start() { return (this.useServer ? this.recording : this.browser).start(); }

    finish() {
      if (this.recording.active) this.recording.finish();
      else this.browser.finish();
    }

    cancel() {
      this.recording.cancel();
      this.browser.cancel();
    }
  }

  root.RecordingListener = RecordingListener;
  root.AutoListener = AutoListener;
  if (typeof module !== "undefined") module.exports = { RecordingListener, AutoListener };
})(typeof window !== "undefined" ? window : globalThis);
