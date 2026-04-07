import { defineStore } from "pinia";
import type { APIError } from "@/types/api";
import type { ResultsManifestResponse } from "@/types/result";
import { getResultsManifest } from "@/api/results";

export const useResultStore = defineStore("result", {
  state: () => ({
    manifest: null as ResultsManifestResponse | null,
    loading: false as boolean,
    error: null as APIError | null,
  }),
  actions: {
    async fetchManifest(taskId: string) {
      this.error = null;
      this.loading = true;
      try {
        const res = await getResultsManifest(taskId);
        this.manifest = res;
        return res;
      } catch (e) {
        this.error = e as APIError;
        throw e;
      } finally {
        this.loading = false;
      }
    },
  },
});

