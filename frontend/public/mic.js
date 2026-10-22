(function (root) {
  "use strict";

  // Keeps the microphone open for a short while after use, and opens it as soon as the user
  // reaches for the Speak button, so pressing Speak starts capturing at once. The browser's
  // recording indicator stays on during that window, and the stream closes itself when idle.
  const IDLE_MS = 15000;
  const CONSTRAINTS = { audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } };
  const pool = { stream: null, pending: null, timer: null };

  function alive(stream) {
    return Boolean(stream) && stream.getTracks().length > 0 && stream.getTracks().every((track) => track.readyState === "live");
  }

  function close() {
    root.clearTimeout(pool.timer);
    pool.timer = null;
    if (pool.stream) pool.stream.getTracks().forEach((track) => track.stop());
    pool.stream = null;
  }

  const MicPool = {
    isWarm() { return alive(pool.stream); },

    acquire() {
      root.clearTimeout(pool.timer);
      pool.timer = null;
      if (alive(pool.stream)) return Promise.resolve(pool.stream);
      if (!pool.pending) {
        pool.pending = root.navigator.mediaDevices.getUserMedia(CONSTRAINTS)
          .then((stream) => { pool.stream = stream; return stream; })
          .finally(() => { pool.pending = null; });
      }
      return pool.pending;
    },

    // Called when a listener is done with the stream. It stays open for IDLE_MS in case of another phrase.
    release() {
      root.clearTimeout(pool.timer);
      pool.timer = root.setTimeout(close, IDLE_MS);
    },

    // Open the microphone ahead of time. Errors are ignored: the real start reports them.
    warm() {
      if (!root.navigator || !root.navigator.mediaDevices || !root.navigator.mediaDevices.getUserMedia) return;
      MicPool.acquire().then(() => MicPool.release(), () => {});
    },

    close,
  };

  root.MicPool = MicPool;
  if (typeof module !== "undefined") module.exports = { MicPool };
})(typeof window !== "undefined" ? window : globalThis);
