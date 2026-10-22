(function (root) {
  "use strict";

  // Streams the microphone to the server, which relays it to Gemini's live transcriber.
  // Words appear while you speak; a pause (or Done) ends the phrase and sends it on.
  const SILENCE_MS = 1100;
  const NO_SPEECH_MS = 8000;
  const MAX_MS = 30000;
  const CONNECT_MS = 4000;
  const DONE_WAIT_MS = 8000;
  const WORKLET_URL = new URL(
    "pcm-worklet.js",
    (root.document && root.document.currentScript && root.document.currentScript.src) || root.location.href,
  ).href;

  class LiveListener {
    constructor({ onState, onTranscript, onStatus, onUtterance, onError }) {
      this.onState = onState;
      this.onTranscript = onTranscript;
      this.onStatus = onStatus || (() => {});
      this.onUtterance = onUtterance;
      this.onError = onError;
      this.onFailure = () => {};
      this.session = null;
    }

    get active() { return this.session !== null; }

    // Resolves true when it handled the request (even with an error shown), false when live
    // transcription could not start and the caller should record and upload instead.
    async start() {
      if (this.active) return true;
      const media = root.navigator && root.navigator.mediaDevices;
      if (!media || !media.getUserMedia || !root.WebSocket || !root.AudioWorkletNode) return false;
      const session = {
        ws: null, stream: null, context: null, node: null, finals: [], interim: "",
        heard: false, lastVoice: 0, floor: null, started: Date.now(), ended: false, timers: {},
      };
      this.session = session;
      this.onTranscript("");
      this.onState(true);
      this.onStatus(root.MicPool && root.MicPool.isWarm() ? "Listening… pause when you finish" : "Starting microphone…");
      // Ask for the microphone and open the connection at the same time, so neither waits on the other.
      const streaming = root.MicPool
        ? root.MicPool.acquire()
        : media.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
      const connecting = this.connect(session);
      connecting.catch(() => {});
      try {
        session.stream = await streaming;
      } catch (error) {
        this.drop(session);
        this.onError("The microphone did not start. Check permission and try again.");
        return true;
      }
      if (this.session !== session) { this.release(session); return true; }
      try {
        await connecting;
        await this.capture(session);
      } catch (error) {
        if (this.session !== session) return true;
        this.release(session);
        this.session = null;
        this.onState(false);
        return false;
      }
      if (this.session !== session) { this.release(session); return true; }
      this.onStatus("Listening… pause when you finish");
      session.timers.poll = root.setInterval(() => this.check(session), 100);
      return true;
    }

    connect(session) {
      const scheme = root.location.protocol === "https:" ? "wss" : "ws";
      const ws = new root.WebSocket(`${scheme}://${root.location.host}/api/transcribe/live`);
      session.ws = ws;
      ws.binaryType = "arraybuffer";
      return new Promise((resolve, reject) => {
        const timer = root.setTimeout(() => reject(new Error("timeout")), CONNECT_MS);
        ws.onopen = () => { root.clearTimeout(timer); resolve(); };
        ws.onerror = () => { root.clearTimeout(timer); reject(new Error("socket")); };
        ws.onclose = () => { root.clearTimeout(timer); reject(new Error("closed")); };
      }).then(() => {
        ws.onerror = null;
        ws.onclose = () => this.closed(session);
        ws.onmessage = (event) => this.message(session, event);
      });
    }

    async capture(session) {
      const Context = root.AudioContext || root.webkitAudioContext;
      session.context = new Context({ sampleRate: 16000 });
      await session.context.audioWorklet.addModule(WORKLET_URL);
      const source = session.context.createMediaStreamSource(session.stream);
      session.node = new root.AudioWorkletNode(session.context, "pcm-capture");
      session.node.port.onmessage = (event) => this.audio(session, event.data);
      source.connect(session.node);
    }

    audio(session, { pcm, rms }) {
      if (this.session !== session || session.ended) return;
      if (session.ws.readyState === 1) session.ws.send(pcm);
      const now = Date.now();
      session.floor = session.floor === null ? rms : Math.min(session.floor, rms);
      // The quietest moment so far is the room noise; speech must clearly rise above it.
      if (rms > Math.max(0.02, Math.min(session.floor * 3, 0.05))) {
        session.heard = true;
        session.lastVoice = now;
      }
    }

    check(session) {
      if (this.session !== session || session.ended) return;
      const now = Date.now();
      if (session.heard && now - session.lastVoice > SILENCE_MS) this.finish();
      else if (!session.heard && now - session.started > NO_SPEECH_MS) {
        this.cancel();
        this.onError("Didn't catch speech. Move closer to the mic and try again.");
      } else if (now - session.started > MAX_MS) this.finish();
    }

    message(session, event) {
      if (this.session !== session) return;
      let data;
      try { data = JSON.parse(event.data); } catch (error) { return; }
      const heard = () => [...session.finals, session.interim].filter(Boolean).join(" ");
      if (data.type === "partial") {
        session.interim = data.text;
        this.onTranscript(heard());
      } else if (data.type === "final") {
        session.finals.push(data.text);
        session.interim = "";
        this.onTranscript(heard());
      } else if (data.type === "done") {
        this.complete(session, data.text || heard());
      } else if (data.type === "error") {
        this.drop(session);
        this.onFailure();
        this.onError(`${data.message || "Live transcription failed."} Using standard transcription, please say it again.`);
      }
    }

    closed(session) {
      if (this.session !== session) return;
      const text = [...session.finals, session.interim].filter(Boolean).join(" ");
      if (session.ended && text) this.complete(session, text);
      else {
        this.drop(session);
        this.onFailure();
        this.onError("The connection to live transcription closed. Using standard transcription, please say it again.");
      }
    }

    finish() {
      const session = this.session;
      if (!session || session.ended) return;
      session.ended = true;
      root.clearInterval(session.timers.poll);
      this.stopCapture(session);
      this.onState(false);
      this.onStatus("Transcribing…");
      try { session.ws.send(JSON.stringify({ type: "end" })); } catch (error) { /* closed */ }
      session.timers.wait = root.setTimeout(() => {
        const text = [...session.finals, session.interim].filter(Boolean).join(" ");
        if (text) this.complete(session, text);
        else { this.drop(session); this.onError("Didn't catch a complete sentence. Please try again or type it."); }
      }, DONE_WAIT_MS);
    }

    complete(session, text) {
      this.drop(session);
      const heard = (text || "").trim();
      if (!heard) {
        this.onError("Didn't catch a complete sentence. Please try again or type it.");
        return;
      }
      this.onTranscript(heard);
      this.onUtterance(heard);
    }

    cancel() {
      const session = this.session;
      if (session) this.drop(session);
    }

    drop(session) {
      const wasListening = !session.ended;
      session.ended = true;
      this.release(session);
      if (this.session === session) {
        this.session = null;
        if (wasListening) this.onState(false);
      }
    }

    stopCapture(session) {
      try { session.node && session.node.disconnect(); } catch (error) { /* gone */ }
      if (session.stream) {
        if (root.MicPool) root.MicPool.release();
        else session.stream.getTracks().forEach((track) => track.stop());
      }
      try { session.context && session.context.close(); } catch (error) { /* closed */ }
      session.stream = null;
      session.context = null;
      session.node = null;
    }

    release(session) {
      root.clearInterval(session.timers.poll);
      root.clearTimeout(session.timers.wait);
      this.stopCapture(session);
      try { if (session.ws) { session.ws.onclose = null; session.ws.close(); } } catch (error) { /* closed */ }
    }
  }

  root.LiveListener = LiveListener;
  if (typeof module !== "undefined") module.exports = { LiveListener };
})(typeof window !== "undefined" ? window : globalThis);
