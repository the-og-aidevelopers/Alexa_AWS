// Turns microphone audio into 100 ms blocks of 16 kHz, 16-bit mono PCM for the live transcriber.
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.position = 0;
    this.pending = [];
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input) return true;
    for (let i = 0; i < input.length; i += 1) {
      this.position += 1;
      if (this.position >= this.ratio) {
        this.position -= this.ratio;
        this.pending.push(input[i]);
      }
    }
    while (this.pending.length >= 1600) {
      const block = this.pending.splice(0, 1600);
      const pcm = new Int16Array(1600);
      let sum = 0;
      for (let i = 0; i < 1600; i += 1) {
        const value = Math.max(-1, Math.min(1, block[i]));
        pcm[i] = value < 0 ? value * 32768 : value * 32767;
        sum += value * value;
      }
      this.port.postMessage({ pcm: pcm.buffer, rms: Math.sqrt(sum / 1600) }, [pcm.buffer]);
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCapture);
