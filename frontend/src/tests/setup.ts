import { config, enableAutoUnmount } from "@vue/test-utils";
import { afterEach, vi } from "vitest";

config.global.mocks = {
  ...(config.global.mocks || {}),
  $t: (key: string) => key,
};

if (!(globalThis as { __VTU_AUTO_UNMOUNT__?: boolean }).__VTU_AUTO_UNMOUNT__) {
  enableAutoUnmount(afterEach);
  (globalThis as { __VTU_AUTO_UNMOUNT__?: boolean }).__VTU_AUTO_UNMOUNT__ = true;
}

afterEach(() => {
  localStorage.clear();
  vi.clearAllTimers();
  vi.clearAllMocks();
  vi.restoreAllMocks();
  vi.useRealTimers();
  document.body.innerHTML = "";
});
