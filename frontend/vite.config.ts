import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The frontend talks to the backend through a proxy so the browser only ever
// sees same-origin /api/* calls (no CORS setup needed in dev). The backend
// serves routes WITHOUT an /api prefix (e.g. /applications), so we strip the
// /api segment on the way through: /api/applications -> :8000/applications.
export default defineConfig({
  plugins: [react(), tailwindcss()],
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
