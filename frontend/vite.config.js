import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev mode (npm run dev, port 5173) API calls are proxied to FastAPI on :8000.
// In production FastAPI serves the built files itself, so no proxy is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000", "/hls": "http://127.0.0.1:8000" },
  },
});
