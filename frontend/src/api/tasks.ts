import { apiRequest, UPLOAD_TIMEOUT_MS } from "@/api/client";
import type { RecentTask, TaskStatusResponse, UploadTaskResponse } from "@/types/task";
import type { SubtitleFormat } from "@/types/subtitle";

export async function createUploadTask(formData: FormData): Promise<UploadTaskResponse> {
  return apiRequest<UploadTaskResponse>("/upload", {
    method: "POST",
    body: formData,
    timeoutMs: UPLOAD_TIMEOUT_MS,
    timeoutMessage: "Upload timeout",
  });
}

export async function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  return apiRequest<TaskStatusResponse>(`/status/${encodeURIComponent(taskId)}`);
}

export async function getRecentTasks(): Promise<RecentTask[]> {
  return apiRequest<RecentTask[]>("/tasks/recent");
}

export interface RebuildFinalVideoResponse {
  status: string;
  task_id: string;
  rebuild_task_id: string;
}

export async function rebuildFinalVideo(taskId: string, lang: string, format: SubtitleFormat): Promise<RebuildFinalVideoResponse> {
  const q = new URLSearchParams({ lang, format }).toString();
  return apiRequest<RebuildFinalVideoResponse>(`/tasks/${encodeURIComponent(taskId)}/rebuild-final?${q}`, {
    method: "POST",
  });
}

export async function cancelTask(taskId: string): Promise<{ status: string; task_id: string }> {
  return apiRequest<{ status: string; task_id: string }>(`/tasks/${encodeURIComponent(taskId)}/cancel`, {
    method: "POST",
  });
}
