const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

function setup({ failStart = false } = {}) {
  const timers = new Map();
  const instances = [];
  const states = [], previews = [], sent = [], errors = [];
  let next = 0;
  class Recognition {
    constructor() { instances.push(this); }
    start() { if (failStart) throw new Error("permission denied"); }
    stop() { this.stopped = true; }
    abort() { this.aborted = true; }
    result(...results) { this.onresult({ results }); }
    end() { this.onend(); }
    error(error) { this.onerror({ error }); }
  }
  const context = vm.createContext({
    window: { SpeechRecognition: Recognition, navigator: { language: "en-IN" } },
    setTimeout(callback, delay) { timers.set(++next, { callback, delay }); return next; },
    clearTimeout(id) { timers.delete(id); },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../web/listener.js"), "utf8"), context);
  const listener = new context.window.SpeechListener({
    onState: (state) => states.push(state),
    onTranscript: (text) => previews.push(text),
    onUtterance: (text) => sent.push(text),
    onError: (text) => errors.push(text),
  });
  function fire(delay) {
    for (const [id, timer] of [...timers]) {
      if (timer.delay === delay && timers.has(id)) {
        timers.delete(id);
        timer.callback();
      }
    }
  }
  return { listener, instances, timers, states, previews, sent, errors, fire };
}

function result(text, isFinal = true, alternative = "") {
  const piece = [{ transcript: text }];
  if (alternative) piece.push({ transcript: alternative });
  piece.isFinal = isFinal;
  return piece;
}

test("final recognition replaces a longer obsolete interim guess", () => {
  const t = setup(); t.listener.start();
  const mic = t.instances[0];
  mic.result(result("I skipped the evening medicine yesterday", false));
  mic.result(result("I took the morning one"));
  mic.end();
  assert.deepEqual(t.sent, ["I took the morning one"]);
});

test("multiple final segments form the full command and reason", () => {
  const t = setup(); t.listener.start();
  t.instances[0].result(result("I skipped the evening one,"), result("I feel dizzy"));
  t.instances[0].end();
  assert.deepEqual(t.sent, ["I skipped the evening one, I feel dizzy"]);
});

test("the preferred alternative wins, rather than the longest alternative", () => {
  const t = setup(); t.listener.start();
  t.instances[0].result(result("I took the morning one", true, "I skipped the evening medicine"));
  t.instances[0].end();
  assert.deepEqual(t.sent, ["I took the morning one"]);
});

test("repeated session results do not duplicate previous segments", () => {
  const t = setup(); t.listener.start();
  const mic = t.instances[0];
  mic.result(result("Raj needs medicine"), result("at eight", false));
  mic.result(result("Raj needs medicine"), result("at 8 AM and 8 PM"));
  mic.end();
  assert.deepEqual(t.sent, ["Raj needs medicine at 8 AM and 8 PM"]);
});

test("removed interim results disappear from the preview", () => {
  const t = setup(); t.listener.start();
  const mic = t.instances[0];
  mic.result(result("I took", true), result("a wrong guess", false));
  mic.result(result("I took", true));
  assert.equal(t.previews.at(-1), "I took");
});

test("pause requests stop, then waits for the final result and end", () => {
  const t = setup(); t.listener.start();
  const mic = t.instances[0];
  mic.result(result("I skipped", false));
  t.fire(1200);
  assert.equal(mic.stopped, true);
  assert.equal(t.sent.length, 0);
  mic.result(result("I took the morning one"));
  mic.end();
  assert.deepEqual(t.sent, ["I took the morning one"]);
  assert.equal(t.timers.size, 0);
});

test("Done, end, and timeout cannot submit the same utterance twice", () => {
  const t = setup(); t.listener.start();
  const mic = t.instances[0];
  mic.result(result("What's due now?"));
  t.listener.finish(); t.listener.finish(); mic.end(); mic.end();
  t.fire(1500); t.fire(20000);
  assert.deepEqual(t.sent, ["What's due now?"]);
});

test("interim-only speech never writes a dose", () => {
  const t = setup(); t.listener.start();
  t.instances[0].result(result("I took medicine", false));
  t.instances[0].end();
  assert.equal(t.sent.length, 0);
  assert.equal(t.errors.length, 1);
});

test("no speech clears every timer, allowing a clean retry", () => {
  const t = setup(); t.listener.start();
  t.instances[0].error("no-speech");
  assert.equal(t.listener.active, false);
  assert.equal(t.timers.size, 0);
  t.listener.start();
  t.instances[1].result(result("What's due now?"));
  t.instances[1].end();
  assert.deepEqual(t.sent, ["What's due now?"]);
});

test("permission error discards partial speech and resets the listener", () => {
  const t = setup(); t.listener.start();
  const mic = t.instances[0];
  mic.result(result("I took the morning one"));
  mic.error("not-allowed"); mic.end();
  assert.equal(t.sent.length, 0);
  assert.deepEqual(t.states, [true, false]);
  assert.equal(t.timers.size, 0);
});

test("synchronous start failure resets the session without timers", () => {
  const t = setup({ failStart: true }); t.listener.start();
  assert.equal(t.listener.active, false);
  assert.equal(t.timers.size, 0);
  assert.deepEqual(t.states, [true, false]);
  assert.equal(t.errors.length, 1);
});

test("rapid starts and old callbacks cannot overwrite the new session", () => {
  const t = setup(); t.listener.start(); t.listener.start();
  assert.equal(t.instances.length, 1);
  const old = t.instances[0];
  t.listener.cancel(); t.listener.start();
  old.result(result("I skipped the evening one")); old.end(); old.error("network");
  t.instances[1].result(result("I took the morning one")); t.instances[1].end();
  assert.deepEqual(t.sent, ["I took the morning one"]);
  assert.equal(t.errors.length, 0);
});

test("maximum duration stops a session and drains a final result", () => {
  const t = setup(); t.listener.start();
  t.fire(20000);
  assert.equal(t.instances[0].stopped, true);
  t.instances[0].result(result("What's due now?"));
  t.instances[0].end();
  assert.deepEqual(t.sent, ["What's due now?"]);
});

test("missing end event releases the session and aborts the microphone", () => {
  const t = setup(); t.listener.start();
  t.instances[0].result(result("What's due now?"));
  t.listener.finish(); t.fire(1500);
  assert.equal(t.listener.active, false);
  assert.equal(t.instances[0].aborted, true);
  assert.equal(t.timers.size, 0);
  assert.deepEqual(t.sent, ["What's due now?"]);
});
