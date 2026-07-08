import { defineStore } from "pinia";
import type { TaskStatusResponse } from "@/types/task";
import { createUploadTask, getTaskStatus } from "@/api/tasks";
import type { APIError } from "@/types/api";
import { usePreferencesStore } from "@/stores/preferences";

type PollTimer = number | null;

function isTerminalStatus(status: string): boolean {
  const normalizedStatus = String(status).toUpperCase();
  return normalizedStatus === "SUCCESS" || normalizedStatus === "FAILURE" || normalizedStatus === "CANCELED";
}

export const useTaskStore = defineStore("task", {
  state: () => ({
    taskId: "" as string,
    status: "PENDING" as string,
    progress: 0 as number,
    message: "" as string,
    result_task_id: null as string | null,
    result_url: null as string | null,
    warnings: [] as string[],
    error: null as APIError | null,
    error_code: "" as string,
    suggestion: "" as string,
    pollingTimer: null as PollTimer,
  }),
  actions: {
    resetForTask(taskId: string) {
      if (this.taskId === taskId) return;
      this.taskId = taskId;
      this.status = "PENDING";
      this.progress = 0;
      this.message = "";
      this.result_task_id = null;
      this.result_url = null;
      this.warnings = [];
      this.error = null;
      this.error_code = "";
      this.suggestion = "";
    },
    async createTask(formData: FormData) {
      this.error = null;
      this.warnings = [];
      const rawLangs = String(formData.get("target_langs") ?? "").trim();
      const first = rawLangs
        .split(",")
        .map((segment) => segment.trim())
        .filter(Boolean)[0];
      if (first) {
        const prefs = usePreferencesStore();
        prefs.setPreferredLang(first.replaceAll(" ", "_"));
      }

      const res = await createUploadTask(formData);
      this.applyStatus(res);
      return res;
    },
    async fetchTaskStatus(taskId: string) {
      this.error = null;
      try {
        const res = await getTaskStatus(taskId);
        this.applyStatus(res);
        if (isTerminalStatus(res.status)) {
          this.stopPolling();
        }
        return res;
      } catch (e) {
        const err = e as APIError;
        this.error = err;
        if (err.status === 404) {
          this.status = "FAILURE";
          this.message = err.message || "Task not found";
          this.error_code = err.error_code ?? "task_not_found";
        }
        this.stopPolling();
        throw err;
      }
    },
    applyStatus(res: TaskStatusResponse) {
      this.taskId = res.task_id;
      this.status = res.status;
      this.progress = res.progress;
      this.message = res.message ?? "";
      this.result_task_id = res.result_task_id ?? null;
      this.result_url = res.result_url ?? null;
      this.warnings = Array.isArray(res.warnings) ? res.warnings : [];
      this.error_code = res.error_code ?? "";
      this.suggestion = res.suggestion ?? "";

      if (res.error_code) {
        this.error = {
          message: res.message ?? "Unknown error",
          error_code: res.error_code,
          suggestion: res.suggestion,
        };
      }
    },
    async startPolling(taskId: string) {
      this.stopPolling();
      this.resetForTask(taskId);

      // Fetch once immediately so terminal states and 404s never leave a dangling interval.
      try {
        await this.fetchTaskStatus(taskId);
      } catch (e) {
        const err = e as APIError;
        this.error = err;
        this.error_code = err.error_code ?? "";
        this.suggestion = err.suggestion ?? "";
      }

      if (isTerminalStatus(this.status) || this.error?.status === 404) return;

      this.pollingTimer = window.setInterval(() => {
        void this.fetchTaskStatus(taskId).catch((e) => {
          this.error = e as APIError;
          this.stopPolling();
        });
      }, 1000);
    },
    stopPolling() {
      if (this.pollingTimer !== null) {
        window.clearInterval(this.pollingTimer);
        this.pollingTimer = null;
      }
    },
  },
});
