import { defineStore } from "pinia";
import type { APIError } from "@/types/api";
import type { ResultsManifestResponse } from "@/types/result";
import { getResultsManifest } from "@/api/results";

export const useResultStore = defineStore("result", {
  state: () => ({
    taskId: null as string | null,
    manifest: null as ResultsManifestResponse | null,
    loading: false as boolean,
    error: null as APIError | null,
  }),
  actions: {
    async fetchManifest(taskId: string) {
      if (this.taskId !== taskId) {
        this.taskId = taskId;
        this.manifest = null;
        this.error = null;
      }
      this.error = null;
      this.loading = true;
      try {
        const res = await getResultsManifest(taskId);
        this.manifest = res;
        return res;
      } catch (e) {
        this.error = e as APIError;
        this.manifest = null;
        return null;
      } finally {
        this.loading = false;
      }
    },
  },
});
