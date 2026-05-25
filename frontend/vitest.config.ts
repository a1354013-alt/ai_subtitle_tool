import { mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(viteConfig, {
  test: {
    pool: "forks",
    poolOptions: {
      forks: {
        singleFork: true,
      },
    },
    fileParallelism: false,
    watch: false,
    testTimeout: 10000,
    hookTimeout: 10000,
    teardownTimeout: 10000,
  },
});
