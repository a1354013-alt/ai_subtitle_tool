import { apiRequest, buildApiUrl, buildQuery } from "@/api/client";
import type { ResultsManifestResponse } from "@/types/result";
import type { DownloadSubtitleFormat } from "@/types/subtitle";

export async function getResultsManifest(taskId: string): Promise<ResultsManifestResponse> {
  return apiRequest<ResultsManifestResponse>(`/results/${encodeURIComponent(taskId)}`);
}

export async function createDownloadTicket(path: string): Promise<string> {
  const response = await apiRequest<{ url: string }>(`/download-ticket${buildQuery({ path })}`);
  return buildApiUrl(response.url);
}

// 規格：buildDownloadUrl(taskId, format?, lang?)
// - format 未給表示下載 final video
// - 下載字幕時必須明確給 lang（不要由 localStorage 等隱性狀態決定 URL）
export function buildDownloadUrl(taskId: string, format?: DownloadSubtitleFormat, lang?: string): string {
  const basePath = `/download/${encodeURIComponent(taskId)}`;
  if (!format) return buildApiUrl(basePath);

  if (!lang) {
    throw new Error("buildDownloadUrl(taskId, format, lang): lang is required when downloading subtitles");
  }
  const q = buildQuery({ lang, format });
  return buildApiUrl(`${basePath}${q}`);
}

export function buildDownloadPath(taskId: string, format?: DownloadSubtitleFormat, lang?: string): string {
  const basePath = `/download/${encodeURIComponent(taskId)}`;
  if (!format) return basePath;
  if (!lang) {
    throw new Error("buildDownloadPath(taskId, format, lang): lang is required when downloading subtitles");
  }
  return `${basePath}${buildQuery({ lang, format })}`;
}
