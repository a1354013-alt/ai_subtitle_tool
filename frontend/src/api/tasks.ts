import { apiRequest } from "@/api/client";
import type { TaskStatusResponse, UploadTaskResponse } from "@/types/task";

export async function createUploadTask(formData: FormData): Promise<UploadTaskResponse> {
  return apiRequest<UploadTaskResponse>("/upload", {
    method: "POST",
    body: formData,
  });
}

export async function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  return apiRequest<TaskStatusResponse>(`/status/${encodeURIComponent(taskId)}`);
}

