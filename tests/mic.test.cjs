const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

function setup() {
  let opened = 0;
  const timers = new Map();
  let next = 0;
  const makeStream = () => {
    const track = { readyState: "live", stop() { this.readyState = "ended"; } };
    return { track, getTracks: () => [track] };
  };
  const streams = [];
  const context = vm.createContext({
    window: {},
    Promise,
    setTimeout(callback, delay) { timers.set(++next, { callback, delay }); return next; },
    clearTimeout(id) { timers.delete(id); },
  });
  context.window.navigator = {
    mediaDevices: { getUserMedia: async () => { opened += 1; const s = makeStream(); streams.push(s); return s; } },
  };
  context.window.setTimeout = context.setTimeout;
  context.window.clearTimeout = context.clearTimeout;
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/public/mic.js"), "utf8"), context);
  return { pool: context.window.MicPool, opened: () => opened, streams, timers };
}

test("warming opens the microphone once, so the next start is instant", async () => {
  const t = setup();
  assert.equal(t.pool.isWarm(), false);
  t.pool.warm();
  t.pool.warm();
  await t.pool.acquire();
  assert.equal(t.opened(), 1);
  assert.equal(t.pool.isWarm(), true);
  const again = await t.pool.acquire();
  assert.equal(t.opened(), 1);
  assert.equal(again, t.streams[0]);
});

test("the microphone closes itself after the idle window and reopens on demand", async () => {
  const t = setup();
  await t.pool.acquire();
  t.pool.release();
  assert.equal(t.timers.size, 1);
  assert.equal([...t.timers.values()][0].delay, 15000);
  [...t.timers.values()][0].callback();
  assert.equal(t.streams[0].track.readyState, "ended");
  assert.equal(t.pool.isWarm(), false);
  await t.pool.acquire();
  assert.equal(t.opened(), 2);
});

test("acquiring again cancels the pending close", async () => {
  const t = setup();
  await t.pool.acquire();
  t.pool.release();
  await t.pool.acquire();
  assert.equal(t.timers.size, 0);
});
