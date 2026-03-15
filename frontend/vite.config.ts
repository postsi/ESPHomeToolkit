import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  base: "/api/esptoolkit/static/",
  build: {
    outDir: path.resolve(__dirname, "../custom_components/esptoolkit/web/dist"),
    emptyOutDir: true,
    sourcemap: true,
  },
});
