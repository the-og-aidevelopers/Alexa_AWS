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
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/public/listener.js"), "utf8"), context);
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

test("a dose-shaped alternative beats address and docomo", () => {
  const t = setup(); t.listener.start();
  t.instances[0].result(result("address Docomo at 8:00 a.m.", true, "add Raj dopamine at 8 AM"));
  t.instances[0].end();
  assert.deepEqual(t.sent, ["add Raj dopamine at 8 AM"]);
});

test("a short pause does not restart recognition or split the sentence", () => {
  const t = setup(); t.listener.start();
  const mic = t.instances[0];
  mic.result(result("Raj", false));
  assert.equal(t.timers.size > 0, true);
  mic.result(result("Raj needs dopamine at 8 AM"));
  t.fire(1800);
  mic.end();
  assert.equal(t.instances.length, 1);
  assert.deepEqual(t.sent, ["Raj needs dopamine at 8 AM"]);
});

test("the preferred alternative wins, rather than the longest alternative", () => {
  const t = setup(); t.listener.start();
  t.instances[0].result(result("I took the morning one", true, "I skipped the evening medicine"));
  t.instances[0].end();
  assert.deepEqual(t.sent, ["I took the morning one"]);
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
