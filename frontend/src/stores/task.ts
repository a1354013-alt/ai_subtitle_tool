import { defineStore } from "pinia";
import type { TaskStatusResponse } from "@/types/task";
import { createUploadTask, getTaskStatus } from "@/api/tasks";
import type { APIError } from "@/types/api";
import { setPreferredLang } from "@/api/subtitles";

type PollTimer = number | null;

function isTerminalStatus(status: string): boolean {
  const s = String(status).toUpperCase();
  return s === "SUCCESS" || s === "FAILURE" || s === "REVOKED";
}

export const useTaskStore = defineStore("task", {
  state: () => ({
    taskId: "" as string,
    status: "PENDING" as string,
    progress: 0 as number,
    message: "" as string,
    error: null as APIError | null,
    pollingTimer: null as PollTimer,
  }),
  actions: {
    async createTask(formData: FormData) {
      this.error = null;
      const rawLangs = String(formData.get("target_langs") ?? "").trim();
      const first = rawLangs.split(",").map((s) => s.trim()).filter(Boolean)[0];
      if (first) setPreferredLang(first.replaceAll(" ", "_"));

      const res = await createUploadTask(formData);
      this.applyStatus(res);
      return res;
    },
    async fetchTaskStatus(taskId: string) {
      this.error = null;
      const res = await getTaskStatus(taskId);
      this.applyStatus(res);
      if (isTerminalStatus(res.status)) {
        this.stopPolling();
      }
      return res;
    },
    applyStatus(res: TaskStatusResponse) {
      this.taskId = res.task_id;
      this.status = res.status;
      this.progress = res.progress;
      this.message = res.message ?? "";
    },
    async startPolling(taskId: string) {
      this.stopPolling();
      this.taskId = taskId;

      // 先抓一次，避免「任務已終態但仍建立 timer」的競態條件
      try {
        await this.fetchTaskStatus(taskId);
      } catch (e) {
        this.error = e as APIError;
      }

      if (isTerminalStatus(this.status)) return;

      this.pollingTimer = window.setInterval(() => {
        void this.fetchTaskStatus(taskId).catch((e) => {
          this.error = e as APIError;
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
