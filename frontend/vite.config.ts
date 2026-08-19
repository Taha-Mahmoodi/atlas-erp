/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api to the FastAPI backend so the SPA and the API share an
// origin in development (no CORS dance); production serves the built assets behind the
// same reverse proxy as the API.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  // TWO entries, one toolchain. `index.html` is the Atlas console; `website.html` is the
  // property's guest-facing site (frontend/src/modules/hospitality/website/), which is served
  // from its own origin behind its own nginx because it authenticates to the API with a machine
  // key rather than a session. They share types and the build, never a bundle entry.
  build: {
    rollupOptions: {
      input: {
        console: fileURLToPath(new URL("./index.html", import.meta.url)),
        website: fileURLToPath(new URL("./website.html", import.meta.url)),
      },
    },
  },
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
  test: {
    environment: "jsdom",
    // globals so @testing-library/react registers its afterEach auto-cleanup —
    // without it every render accumulates in one DOM and events hit stale mocks.
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.tsx", "src/**/*.test.ts"],
  },
});
