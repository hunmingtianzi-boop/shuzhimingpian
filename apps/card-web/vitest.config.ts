import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: {
    dedupe: ["react", "react-dom"],
    // Worktrees may retain a workspace junction created elsewhere. Tests must
    // exercise this checkout's shared renderer, just like the Vite app does.
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
  },
});
