import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite 7 (rollup-based) is pinned deliberately. Vite 8 uses rolldown, whose
// native binding fails to install on this machine via npm's optional-dependency
// bug (npm/cli#4828) -- a fresh `npm install` produced a build that could not
// run. See PROJECT_STATE.md -> Known Bugs / Technical Debt.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The API is called directly at http://localhost:8000/api (CORS is enabled
    // backend-side). This proxy is the fallback path: point VITE_API_URL at
    // "/api" and requests route through the dev server instead, which sidesteps
    // CORS entirely if it ever misbehaves.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    // Leaflet + Recharts + React Router push past the 500 kB default warning.
    // Not worth code-splitting for a single-bundle dashboard.
    chunkSizeWarningLimit: 1200,
  },
});
