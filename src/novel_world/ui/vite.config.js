import { defineConfig } from "vite";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const webDist = resolve(__dirname, "../web/static/dist");

export default defineConfig({
  build: {
    emptyOutDir: true,
    outDir: webDist,
    rollupOptions: {
      input: resolve(__dirname, "main.js"),
      output: {
        entryFileNames: "app.js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith(".css")) return "app.css";
          return "[name][extname]";
        },
      },
    },
    cssCodeSplit: false,
  },
});
