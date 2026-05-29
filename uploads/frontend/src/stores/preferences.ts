import { defineStore } from "pinia";

const PREFERRED_LANG_KEY = "ai_subtitle_tool_preferred_lang";

function readPreferredLang(): string {
  try {
    return localStorage.getItem(PREFERRED_LANG_KEY) || "Traditional_Chinese";
  } catch {
    return "Traditional_Chinese";
  }
}

function writePreferredLang(lang: string): void {
  try {
    localStorage.setItem(PREFERRED_LANG_KEY, lang);
  } catch {
    // ignore (private browsing / storage disabled)
  }
}

export const usePreferencesStore = defineStore("preferences", {
  state: () => ({
    preferredLang: readPreferredLang() as string,
  }),
  actions: {
    setPreferredLang(lang: string) {
      this.preferredLang = lang;
      writePreferredLang(lang);
    },
  },
});

