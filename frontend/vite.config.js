import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "^/api/v1/(chat|pending-actions|memory)(/|$)": {
        target: "http://127.0.0.1:8005",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
