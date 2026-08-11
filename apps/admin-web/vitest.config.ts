import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    dedupe: ["react", "react-dom"],
    alias: {
      react: fileURLToPath(new URL("./node_modules/react", import.meta.url)),
      "react-dom": fileURLToPath(new URL("./node_modules/react-dom", import.meta.url)),
      "@cf/card-page-renderer": fileURLToPath(
        new URL("../../packages/card-page-renderer/src/index.ts", import.meta.url),
      ),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    clearMocks: true,
    // Fluent UI's modalizer and portal focus state is window-scoped. Running
    // multiple jsdom files concurrently on a constrained CI runner causes
    // nondeterministic aria-hidden transitions and starves unrelated async
    // resource assertions. Keep admin unit tests deterministic and isolated.
    fileParallelism: false,
    maxWorkers: 1,
  },
});
