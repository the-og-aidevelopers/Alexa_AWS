const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

function setup({ transcribe = true, reply = { text: "Raj took his dopamine" }, ok = true } = {}) {
  const sent = [], errors = [], states = [], posts = [];
  let interval = null;
  let level = 0;
  class Recorder {
    constructor() { this.state = "inactive"; this.mimeType = "audio/webm"; }
    static isTypeSupported() { return true; }
    start() { this.state = "recording"; }
    stop() {
      this.state = "inactive";
      this.ondataavailable({ data: new Blob([new Uint8Array(4000)]) });
      this.onstop();
    }
  }
  class Context {
    createAnalyser() { return { fftSize: 0, getFloatTimeDomainData(buffer) { buffer.fill(level); } }; }
    createMediaStreamSource() { return { connect() {} }; }
    close() {}
  }
  const stopped = [];
  const context = vm.createContext({
    window: {},
    Blob, Float32Array, Uint8Array, Date, Promise,
    setInterval(callback) { interval = callback; return 1; },
    clearInterval() { interval = null; },
    setTimeout, clearTimeout,
  });
  context.window.SpeechListener = class { constructor() { this.active = false; } start() { this.usedBrowser = true; } finish() {} cancel() {} };
  context.window.navigator = { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => stopped.push(1) }] }) } };
  context.window.MediaRecorder = Recorder;
  context.window.AudioContext = Context;
  context.window.fetch = async (url, options) => {
    if (url === "/api/health") return { json: async () => ({ capabilities: { transcribe } }) };
    posts.push({ url, options });
    return { ok, json: async () => reply };
  };
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../web/recorder.js"), "utf8"), context);
  const handlers = {
    onState: (value) => states.push(value),
    onTranscript() {}, onStatus() {},
    onUtterance: (text) => sent.push(text),
    onError: (text) => errors.push(text),
  };
  const listener = new context.window.AutoListener(handlers);
  return { listener, sent, errors, states, posts, stopped, tick: () => interval && interval(), setLevel: (value) => { level = value; } };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

test("the server transcriber is used when the server offers it, and it sends the recording", async () => {
  const t = setup();
  await t.listener.ready;
  await t.listener.start();
  t.setLevel(0.001); t.tick();
  t.setLevel(0.3); t.tick();
  t.listener.finish();
  await flush(); await flush();
  assert.equal(t.posts.length, 1);
  assert.equal(t.posts[0].url, "/api/transcribe");
  assert.deepEqual(t.sent, ["Raj took his dopamine"]);
  assert.equal(t.stopped.length > 0, true);
  assert.equal(t.listener.active, false);
});

test("without server transcription the browser engine is used", async () => {
  const t = setup({ transcribe: false });
  await t.listener.ready;
  await t.listener.start();
  assert.equal(t.listener.browser.usedBrowser, true);
  assert.equal(t.posts.length, 0);
});

test("cancel discards the recording", async () => {
  const t = setup();
  await t.listener.ready;
  await t.listener.start();
  t.listener.cancel();
  await flush();
  assert.equal(t.posts.length, 0);
  assert.deepEqual(t.sent, []);
});

test("a failed transcription reports the server's message", async () => {
  const t = setup({ ok: false, reply: { error: "Transcription failed: boom" } });
  await t.listener.ready;
  await t.listener.start();
  t.listener.finish();
  await flush(); await flush();
  assert.deepEqual(t.sent, []);
  assert.deepEqual(t.errors, ["Transcription failed: boom"]);
});
