import { config } from "@vue/test-utils";
import { afterEach } from "vitest";

config.global.mocks = {
  ...(config.global.mocks || {}),
  $t: (key: string) => key,
};

afterEach(() => {
  localStorage.clear();
});
