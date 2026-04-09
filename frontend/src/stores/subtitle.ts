import { defineStore } from "pinia";
import type { SubtitleFormat } from "@/types/subtitle";
import type { APIError } from "@/types/api";
import { getSubtitle, updateSubtitle } from "@/api/subtitles";

export const useSubtitleStore = defineStore("subtitle", {
  state: () => ({
    taskId: null as string | null,
    // Current selection for the active task (task-scoped state).
    // User preference (localStorage) is handled in the page layer via getPreferredLang/setPreferredLang.
    lang: "" as string,
    format: "ass" as SubtitleFormat,
    content: "" as string,
    isDirty: false as boolean,
    loading: false as boolean,
    saving: false as boolean,
    error: null as APIError | null,
    lastSavedAt: null as number | null,
  }),
  actions: {
    resetForTask(taskId: string) {
      if (this.taskId === taskId) return;
      this.taskId = taskId;
      this.lang = "";
      this.format = "ass";
      this.content = "";
      this.isDirty = false;
      this.loading = false;
      this.saving = false;
      this.error = null;
      this.lastSavedAt = null;
    },
    setLang(lang: string) {
      this.lang = lang;
    },
    setFormat(format: SubtitleFormat) {
      this.format = format;
    },
    setContent(content: string) {
      this.content = content;
      this.isDirty = true;
    },
    markClean() {
      this.isDirty = false;
    },
    async fetchSubtitle(taskId: string, lang: string, format: SubtitleFormat) {
      this.resetForTask(taskId);
      this.error = null;
      this.loading = true;
      this.lang = lang;
      this.format = format;
      try {
        const res = await getSubtitle(taskId, lang, format);
        this.content = res.content;
        this.isDirty = false;
      } catch (e) {
        this.error = e as APIError;
        throw e;
      } finally {
        this.loading = false;
      }
    },
    async updateSubtitle(taskId: string, lang: string, format: SubtitleFormat, content: string) {
      this.error = null;
      this.saving = true;
      try {
        await updateSubtitle(taskId, lang, format, content);
        this.content = content;
        this.isDirty = false;
        this.lastSavedAt = Date.now();
      } catch (e) {
        this.error = e as APIError;
        throw e;
      } finally {
        this.saving = false;
      }
    },
  },
});
