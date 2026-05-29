import { apiRequest } from "@/api/client";
import type { RecentTask, TaskStatusResponse, UploadTaskResponse } from "@/types/task";
import type { SubtitleFormat } from "@/types/subtitle";

export async function createUploadTask(formData: FormData): Promise<UploadTaskResponse> {
  return apiRequest<UploadTaskResponse>("/upload", {
    method: "POST",
    body: formData,
  });
}

export async function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  return apiRequest<TaskStatusResponse>(`/status/${encodeURIComponent(taskId)}`);
}

export async function getRecentTasks(): Promise<RecentTask[]> {
  return apiRequest<RecentTask[]>("/tasks/recent");
}

export async function rebuildFinalVideo(taskId: string, lang: string, format: SubtitleFormat): Promise<{ status: string; task_id: string }> {
  const q = new URLSearchParams({ lang, format }).toString();
  return apiRequest<{ status: string; task_id: string }>(`/tasks/${encodeURIComponent(taskId)}/rebuild-final?${q}`, {
    method: "POST",
  });
}

export async function cancelTask(taskId: string): Promise<{ status: string; task_id: string }> {
  return apiRequest<{ status: string; task_id: string }>(`/tasks/${encodeURIComponent(taskId)}/cancel`, {
    method: "POST",
  });
}

