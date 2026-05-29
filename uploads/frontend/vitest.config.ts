import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/tests/setup.ts"],
      include: ["src/**/*.{test,spec}.ts"],
      exclude: [
        "**/node_modules/**",
        "**/dist/**",
        "**/.npm-cache/**",
        "**/.vite/**",
        "**/coverage/**",
      ],
      testTimeout: 10_000,
      hookTimeout: 10_000,
      pool: "forks",
      minWorkers: 1,
      maxWorkers: 1,
      isolate: true,
      clearMocks: true,
      restoreMocks: true,
      coverage: {
        exclude: [
          "**/node_modules/**",
          "**/dist/**",
          "**/.npm-cache/**",
          "**/coverage/**",
          "src/tests/**",
        ],
      },
    },
  })
);
