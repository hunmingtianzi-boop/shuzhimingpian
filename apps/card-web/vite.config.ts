import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "../..", "VITE_");
  const apiProxyTarget =
    env.VITE_DEV_API_PROXY_TARGET?.trim() || "http://127.0.0.1:8000";

  return {
    envDir: "../..",
    plugins: [react(), tailwindcss()],
    resolve: {
      dedupe: ["react", "react-dom"],
      // Resolve the shared renderer from this worktree instead of following a
      // potentially stale workspace symlink created by another worktree.
      alias: {
        react: fileURLToPath(new URL("./node_modules/react", import.meta.url)),
        "react-dom": fileURLToPath(new URL("./node_modules/react-dom", import.meta.url)),
        "@cf/card-page-renderer": fileURLToPath(
          new URL("../../packages/card-page-renderer/src/index.ts", import.meta.url),
        ),
      },
    },
    server: {
      host: "127.0.0.1",
      port: 4173,
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: "127.0.0.1",
      port: 4173,
    },
  };
});
