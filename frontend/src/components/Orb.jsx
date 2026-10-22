import { useEffect, useRef } from "react";

const SIZE = 360;
const COLORS = { listening: "#f2b84b", speaking: "#9fd6bb", thinking: "#7fb89c", idle: "#6aa488" };

// The waves follow the microphone while listening and move on their own otherwise.
export default function Orb({ mode, analyser, onClick, onWarm }) {
  const canvas = useRef(null);
  const live = useRef({ mode, analyser });
  live.current = { mode, analyser };

  useEffect(() => {
    const element = canvas.current;
    const ctx = element?.getContext?.("2d");
    if (!ctx) return undefined;
    const bins = new Uint8Array(128);
    let frame = 0;
    const draw = () => {
      const { mode: current, analyser: node } = live.current;
      const ratio = window.devicePixelRatio || 1;
      if (element.width !== SIZE * ratio) {
        element.width = SIZE * ratio;
        element.height = SIZE * ratio;
      }
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, SIZE, SIZE);
      if (node && current === "listening") node.getByteFrequencyData(bins);
      const now = performance.now() / 1000;
      const bars = 56;
      const center = SIZE / 2;
      ctx.strokeStyle = COLORS[current] || COLORS.idle;
      ctx.lineCap = "round";
      ctx.lineWidth = 3;
      for (let i = 0; i < bars; i += 1) {
        const angle = (i / bars) * Math.PI * 2 - Math.PI / 2;
        let amp = 5 + Math.abs(Math.sin(now * 1.3 + i * 0.18)) * 5;
        if (current === "listening") {
          const bin = node ? bins[i % bins.length] / 255 : Math.abs(Math.sin(now * 7 + i));
          amp = 8 + bin * 48;
        } else if (current === "speaking") {
          amp = 8 + Math.abs(Math.sin(now * 9 + i * 0.55)) * 34;
        } else if (current === "thinking") {
          amp = 7 + Math.abs(Math.sin(now * 3 + i * 0.25)) * 8;
        }
        const inner = 92;
        ctx.beginPath();
        ctx.moveTo(center + Math.cos(angle) * inner, center + Math.sin(angle) * inner);
        ctx.lineTo(center + Math.cos(angle) * (inner + amp), center + Math.sin(angle) * (inner + amp));
        ctx.stroke();
      }
      frame = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <button type="button" className="orb" data-state={mode} aria-pressed={mode === "listening"} aria-label="Talk" onClick={onClick} onPointerEnter={onWarm} onFocus={onWarm}>
      <canvas ref={canvas} className="waves" width={SIZE} height={SIZE} />
      <span className="core" />
    </button>
  );
}
