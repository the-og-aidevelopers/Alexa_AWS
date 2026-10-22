const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

function setup({ socketOpens = true } = {}) {
  const sent = [], errors = [], states = [], sockets = [];
  let failures = 0;
  let level = 0;
  class Socket {
    constructor(url) {
      this.url = url; this.readyState = 0; this.out = []; sockets.push(this);
      setImmediate(() => {
        if (socketOpens) { this.readyState = 1; this.onopen(); } else this.onerror();
      });
    }
    send(data) { this.out.push(data); }
    close() { this.readyState = 3; }
    receive(message) { this.onmessage({ data: JSON.stringify(message) }); }
  }
  class Context {
    constructor() { this.audioWorklet = { addModule: async () => {} }; }
    createMediaStreamSource() { return { connect(node) { node.source = true; } }; }
    close() {}
  }
  class WorkletNode { constructor() { this.port = {}; } disconnect() {} }
  const stopped = [];
  const context = vm.createContext({
    window: {},
    ArrayBuffer, Uint8Array, JSON, Date, URL, Promise,
    setInterval: () => 1, clearInterval() {}, setTimeout, clearTimeout,
  });
  const win = context.window;
  win.location = { protocol: "http:", host: "localhost:8010", href: "http://localhost:8010/" };
  win.navigator = { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => stopped.push(1) }] }) } };
  win.WebSocket = Socket; win.AudioContext = Context; win.AudioWorkletNode = WorkletNode;
  win.setInterval = context.setInterval; win.clearInterval = context.clearInterval;
  win.setTimeout = setTimeout; win.clearTimeout = clearTimeout;
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/public/live.js"), "utf8"), context);
  const transcripts = [];
  const listener = new win.LiveListener({
    onState: (value) => states.push(value),
    onTranscript: (text) => transcripts.push(text),
    onStatus() {},
    onUtterance: (text) => sent.push(text),
    onError: (text) => errors.push(text),
  });
  listener.onFailure = () => { failures += 1; };
  return { listener, sockets, sent, errors, states, transcripts, stopped, failures: () => failures, setLevel: (v) => { level = v; } };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

test("words appear while speaking and the finished phrase is sent on", async () => {
  const t = setup();
  assert.equal(await t.listener.start(), true);
  const ws = t.sockets[0];
  assert.equal(ws.url, "ws://localhost:8010/api/transcribe/live");
  ws.receive({ type: "partial", text: "Add" });
  ws.receive({ type: "partial", text: "Add Rahul" });
  assert.deepEqual(t.transcripts.slice(-2), ["Add", "Add Rahul"]);
  ws.receive({ type: "final", text: "Add Rahul." });
  t.listener.finish();
  assert.equal(ws.out.at(-1), JSON.stringify({ type: "end" }));
  assert.equal(t.states.at(-1), false);
  ws.receive({ type: "done", text: "Add Rahul. At 8 AM." });
  assert.deepEqual(t.sent, ["Add Rahul. At 8 AM."]);
  assert.equal(t.listener.active, false);
  assert.equal(t.stopped.length > 0, true);
});

test("when the socket cannot open, start reports false so the caller can fall back", async () => {
  const t = setup({ socketOpens: false });
  assert.equal(await t.listener.start(), false);
  assert.equal(t.listener.active, false);
  assert.deepEqual(t.errors, []);
});

test("a server error is shown, live is switched off, and nothing is sent", async () => {
  const t = setup();
  await t.listener.start();
  t.sockets[0].receive({ type: "error", message: "Live transcription is out of credits or quota." });
  assert.match(t.errors[0], /out of credits or quota\. Using standard transcription/);
  assert.equal(t.failures(), 1);
  assert.deepEqual(t.sent, []);
  assert.equal(t.listener.active, false);
});

test("cancel closes the socket and sends nothing", async () => {
  const t = setup();
  await t.listener.start();
  t.listener.cancel();
  assert.equal(t.sockets[0].readyState, 3);
  assert.deepEqual(t.sent, []);
});
