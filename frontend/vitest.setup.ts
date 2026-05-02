import { config } from "@vue/test-utils";
import { afterEach } from "vitest";
import i18n from "./src/i18n";

config.global.plugins = [i18n];
i18n.global.locale.value = "en";

afterEach(() => {
  localStorage.clear();
  i18n.global.locale.value = "en";
});
