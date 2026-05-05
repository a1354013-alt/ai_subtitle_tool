import { config } from "@vue/test-utils";
import { afterEach, vi } from "vitest";

config.global.mocks = {
  ...(config.global.mocks || {}),
  $t: (key: string) => key,
};

afterEach(() => {
  localStorage.clear();
  // Ensure all timers are cleared and mocks are restored after each test
  vi.clearAllMocks();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
