import { config, enableAutoUnmount } from "@vue/test-utils";
import { afterEach, beforeEach, vi } from "vitest";

config.global.mocks = {
  ...(config.global.mocks || {}),
  $t: (key: string) => key,
};

const fetchMock = vi.fn<(input: RequestInfo | URL) => Promise<never>>();
const openMock = vi.fn();
const createObjectUrlMock = vi.fn(() => "blob:mock-url");
const revokeObjectUrlMock = vi.fn();
const AUTO_UNMOUNT_KEY = "__VTU_AUTO_UNMOUNT_ENABLED__";

vi.stubGlobal("fetch", fetchMock);
Object.defineProperty(window, "open", {
  configurable: true,
  writable: true,
  value: openMock,
});
Object.defineProperty(URL, "createObjectURL", {
  configurable: true,
  writable: true,
  value: createObjectUrlMock,
});
Object.defineProperty(URL, "revokeObjectURL", {
  configurable: true,
  writable: true,
  value: revokeObjectUrlMock,
});

if (!(globalThis as Record<string, unknown>)[AUTO_UNMOUNT_KEY]) {
  enableAutoUnmount(afterEach);
  (globalThis as Record<string, unknown>)[AUTO_UNMOUNT_KEY] = true;
}

beforeEach(() => {
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    throw new Error(`Unexpected fetch in test: ${String(input)}`);
  });
  openMock.mockImplementation(() => null);
  createObjectUrlMock.mockReturnValue("blob:mock-url");
});

afterEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  document.body.innerHTML = "";
  vi.clearAllMocks();
  vi.clearAllTimers();
  vi.useRealTimers();
});
