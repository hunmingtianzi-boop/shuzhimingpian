import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "../..", "VITE_");
  const apiProxyTarget =
    process.env.VITE_DEV_API_PROXY_TARGET?.trim() ||
    env.VITE_DEV_API_PROXY_TARGET?.trim() ||
    "http://127.0.0.1:8000";
  const apiBaseUrl =
    process.env.VITE_API_BASE_URL?.trim() || env.VITE_API_BASE_URL?.trim() || "";

  return {
    envDir: "../..",
    plugins: [react()],
    define: {
      "import.meta.env.VITE_API_BASE_URL": JSON.stringify(apiBaseUrl),
    },
    resolve: {
      // A worktree can reuse an external pnpm store. Force libraries such as
      // dnd-kit and the shared renderer onto the app's React instance so
      // editor tests and dev preview never load two hook dispatchers.
      dedupe: ["react", "react-dom"],
      // Worktrees may share dependency stores; pin the shared renderer to the
      // source that belongs to the current checkout so preview and public UI
      // cannot silently fall back to an older worktree implementation.
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
      port: 4174,
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: "127.0.0.1",
      port: 4174,
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [
              {
                name: "react-runtime",
                test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/,
                priority: 3,
              },
              {
                name: "fluent-ui",
                test: /node_modules[\\/](@fluentui|@griffel)[\\/]/,
                priority: 2,
              },
              {
                name: "vendor",
                test: /node_modules[\\/]/,
                priority: 1,
              },
            ],
          },
        },
      },
    },
  };
});
