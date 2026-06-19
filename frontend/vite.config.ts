import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

const frontendDir = dirname(fileURLToPath(import.meta.url));
const workspaceDir = resolve(frontendDir, "..");

function resolveBackendUrl(mode: string): string {
  const workspaceEnv = loadEnv(mode, workspaceDir, "");
  const frontendEnv = loadEnv(mode, frontendDir, "");
  const env = { ...workspaceEnv, ...frontendEnv };
  const explicitUrl = env.VITE_BACKEND_URL || env.LLM_WIKI_BACKEND_URL;
  if (explicitUrl) {
    return explicitUrl;
  }
  const host = env.LLM_WIKI_HOST || "127.0.0.1";
  const port = env.LLM_WIKI_PORT || "8020";
  return `http://${host}:${port}`;
}

export default defineConfig(({ mode }) => {
  const backendUrl = resolveBackendUrl(mode);
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
    },
  };
});
