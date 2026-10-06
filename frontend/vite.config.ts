import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/chat": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/doctors": "http://127.0.0.1:8000",
      "/appointments": "http://127.0.0.1:8000",
      "/availability": "http://127.0.0.1:8000",
      "/evaluate": "http://127.0.0.1:8000",
      "/improve": "http://127.0.0.1:8000",
      "/policy": "http://127.0.0.1:8000",
    },
  },
});
