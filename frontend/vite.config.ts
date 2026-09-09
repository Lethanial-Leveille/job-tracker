// defineConfig comes from vitest/config, not vite: vite's own UserConfig has no
// `test` key, so `tsc -b` fails the build even though vite itself runs fine.
// vitest/config re-exports vite's defineConfig widened to include it.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The frontend talks to the backend through a proxy so the browser only ever
// sees same-origin /api/* calls (no CORS setup needed in dev). The backend
// serves routes WITHOUT an /api prefix (e.g. /applications), so we strip the
// /api segment on the way through: /api/applications -> :8000/applications.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Component tests need a DOM. The pure-logic suites (dedupe, grouping,
  // statuses, gradHint) do not care, and jsdom costs them a few hundred ms, but
  // one environment for the whole suite beats per-file annotations that get
  // forgotten on the next file.
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
