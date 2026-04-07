import { apiRequest, buildApiUrl, buildQuery } from "@/api/client";
import type { ResultsManifestResponse } from "@/types/result";
import { getPreferredLang } from "@/api/subtitles";
import type { SubtitleFormat } from "@/types/subtitle";

export async function getResultsManifest(taskId: string): Promise<ResultsManifestResponse> {
  return apiRequest<ResultsManifestResponse>(`/results/${encodeURIComponent(taskId)}`);
}

// 規格：buildDownloadUrl(taskId, format?, lang?)
// - format 未給表示下載 final video
// - lang 未給時使用偏好語言（可由 UI selector 設定，但不應只靠 localStorage 作唯一控制來源）
export function buildDownloadUrl(taskId: string, format?: SubtitleFormat, lang?: string): string {
  const basePath = `/download/${encodeURIComponent(taskId)}`;
  if (!format) return buildApiUrl(basePath);

  const resolvedLang = lang ?? getPreferredLang();
  const q = buildQuery({ lang: resolvedLang, format });
  return buildApiUrl(`${basePath}${q}`);
}
