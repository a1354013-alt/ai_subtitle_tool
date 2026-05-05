import { mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(viteConfig, {
  test: {
    // Prevent tests from hanging indefinitely
    testTimeout: 10000,
    hookTimeout: 10000,
    teardownTimeout: 10000,
    // Ensure Vitest exits even if there are active handles (like timers)
    forceRerunTriggers: ["**/*.test.ts"],
    // Automatically use fake timers to avoid real-time waiting in tests
    // This helps with polling logic in stores
    fakeTimers: {
      toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"],
    },
  },
});
