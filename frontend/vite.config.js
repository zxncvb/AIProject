import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 13000,
    proxy: {
      "/api": "http://127.0.0.1:18080",
      "/public": "http://127.0.0.1:18080",
      "/healthz": "http://127.0.0.1:18080",
      "/readyz": "http://127.0.0.1:18080",
    },
  },
});
