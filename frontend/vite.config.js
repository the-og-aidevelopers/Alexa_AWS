import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const BACKEND = "http://127.0.0.1:8010";
const sameOrigin = (proxy) =>
  proxy.on("proxyReq", (request) => { if (request.getHeader("origin")) request.setHeader("origin", BACKEND); });

// The Python server serves the build from /static and the pages from /, /agent and /login.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/static/" : "/",
  build: { outDir: "../web/dist", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      // The Python server rejects writes whose Origin is not its own, so present the proxy as the backend.
      "/api": { target: BACKEND, changeOrigin: true, ws: true, configure: sameOrigin },
      "/mcp": { target: BACKEND, changeOrigin: true, configure: sameOrigin },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/setupTests.js",
    globals: true,
  },
}));
