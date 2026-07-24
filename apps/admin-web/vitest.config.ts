import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
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
