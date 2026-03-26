import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  base: "./",
  root: resolve(__dirname, "src/renderer"),
  build: {
    outDir: resolve(__dirname, "out/renderer"),
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src/renderer"),
    },
  },
  server: {
    port: 5173,
  },
});
