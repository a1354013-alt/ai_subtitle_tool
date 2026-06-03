import { config, enableAutoUnmount } from "@vue/test-utils";
import { afterEach, vi } from "vitest";
import type { App } from "vue";
import { createI18n } from "vue-i18n";
import en from "@/i18n/locales/en.json";
import ja from "@/i18n/locales/ja.json";
import zhTW from "@/i18n/locales/zh-TW.json";

const i18nTestPlugin = {
  install(app: App) {
    app.use(
      createI18n({
        legacy: false,
        locale: "en",
        fallbackLocale: "en",
        messages: {
          en,
          ja,
          "zh-TW": zhTW,
        },
      })
    );
  },
};

config.global.plugins = [...(config.global.plugins || []), i18nTestPlugin];

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
