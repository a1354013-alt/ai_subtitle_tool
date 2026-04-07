import { apiRequest, buildQuery } from "@/api/client";
import type { SubtitleFormat, SubtitleResponse, UpdateSubtitlePayload } from "@/types/subtitle";

const PREFERRED_LANG_KEY = "ai_subtitle_tool_preferred_lang";

export function getPreferredLang(): string {
  return localStorage.getItem(PREFERRED_LANG_KEY) || "Traditional_Chinese";
}

export function setPreferredLang(lang: string): void {
  localStorage.setItem(PREFERRED_LANG_KEY, lang);
}

export async function getSubtitle(taskId: string, lang: string, format: SubtitleFormat): Promise<SubtitleResponse> {
  const q = buildQuery({ lang, format });
  return apiRequest<SubtitleResponse>(`/subtitle/${encodeURIComponent(taskId)}${q}`);
}

export async function updateSubtitle(taskId: string, lang: string, format: SubtitleFormat, content: string): Promise<unknown> {
  const payload: UpdateSubtitlePayload = { content, format };
  const q = buildQuery({ lang });
  return apiRequest(`/subtitle/${encodeURIComponent(taskId)}${q}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
