import { apiRequest, buildQuery } from "@/api/client";
import type { SubtitleFormat, SubtitleResponse, UpdateSubtitlePayload, UpdateSubtitleResponse } from "@/types/subtitle";

export async function getSubtitle(taskId: string, lang: string, format: SubtitleFormat): Promise<SubtitleResponse> {
  const q = buildQuery({ lang, format });
  return apiRequest<SubtitleResponse>(`/subtitle/${encodeURIComponent(taskId)}${q}`);
}

export async function updateSubtitle(
  taskId: string,
  lang: string,
  format: SubtitleFormat,
  content: string
): Promise<UpdateSubtitleResponse> {
  const payload: UpdateSubtitlePayload = { content, format };
  const q = buildQuery({ lang });
  return apiRequest<UpdateSubtitleResponse>(`/subtitle/${encodeURIComponent(taskId)}${q}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
