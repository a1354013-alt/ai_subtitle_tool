import { apiRequest, buildApiUrl } from "@/api/client";
import type { BatchStatusResponse, BatchUploadResponse } from "@/types/api";

export async function uploadBatch(formData: FormData): Promise<BatchUploadResponse> {
  return apiRequest<BatchUploadResponse>("/batch/upload", {
    method: "POST",
    body: formData,
  });
}

export async function getBatchStatus(batchId: string): Promise<BatchStatusResponse> {
  return apiRequest<BatchStatusResponse>(`/batch/${encodeURIComponent(batchId)}/status`);
}

export function downloadBatch(batchId: string): string {
  return buildApiUrl(`/batch/${encodeURIComponent(batchId)}/download`);
}
