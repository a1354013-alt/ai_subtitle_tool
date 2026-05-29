import { apiRequest, buildApiUrl, buildQuery } from "@/api/client";
import type { ResultsManifestResponse } from "@/types/result";
import type { DownloadSubtitleFormat } from "@/types/subtitle";

const DOWNLOAD_FORMATS = new Set<DownloadSubtitleFormat>(["ass", "srt", "vtt"]);

export async function getResultsManifest(taskId: string): Promise<ResultsManifestResponse> {
  return apiRequest<ResultsManifestResponse>(`/results/${encodeURIComponent(taskId)}`);
}

// 規格：buildDownloadUrl(taskId, format?, lang?)
// - format 未給表示下載 final video
// - 下載字幕時必須明確給 lang（不要由 localStorage 等隱性狀態決定 URL）
export function buildDownloadUrl(taskId: string, format?: DownloadSubtitleFormat, lang?: string): string {
  const basePath = `/download/${encodeURIComponent(taskId)}`;
  if (!format) return buildApiUrl(basePath);

  if (!DOWNLOAD_FORMATS.has(format)) {
    throw new Error(`Unsupported subtitle format: ${format}`);
  }
  if (!lang) {
    throw new Error("buildDownloadUrl(taskId, format, lang): lang is required when downloading subtitles");
  }
  const q = buildQuery({ lang, format });
  return buildApiUrl(`${basePath}${q}`);
}
