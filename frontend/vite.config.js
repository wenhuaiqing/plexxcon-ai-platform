import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5261,
    strictPort: true,
    // Only the backend's paths are proxied; everything else is a page the SPA owns.
    proxy: {
      "/orb":    { target: "http://localhost:8061", changeOrigin: true },
      "/api":    { target: "http://localhost:8061", changeOrigin: true },
      "/health": { target: "http://localhost:8061", changeOrigin: true },
    },
  },
});
