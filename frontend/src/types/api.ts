export type APIError = {
  message: string;
  status?: number;
  detail?: unknown;
  error_code?: string;
  suggestion?: string;
};

export type ErrorResponse = {
  success: false;
  error_code: string;
  message: string;
  suggestion: string;
};

export type AppConfig = {
  maxUploadSizeMb: number;
  maxBatchFiles: number;
  supportedExtensions: string[];
  batchUploadEnabled: boolean;
  subtitleFormats: string[];
};

export type BatchTaskStatus = "PENDING" | "PROCESSING" | "SUCCESS" | "FAILURE" | "CANCELED";

export type BatchSubtitleDownloadUrls = {
  srt?: string;
  ass?: string;
  vtt?: string;
};

export type BatchDownloadUrls = {
  video?: string;
  subtitles: Record<string, BatchSubtitleDownloadUrls>;
};

export type BatchTaskResponse = {
  task_id: string;
  filename: string;
  status: BatchTaskStatus | string;
  progress: number;
  message?: string | null;
  error?: string | null;
  download_urls?: BatchDownloadUrls | null;
};

export type BatchUploadResponse = {
  batch_id: string;
  tasks: BatchTaskResponse[];
};

export type BatchStatusResponse = {
  batch_id: string;
  total: number;
  completed: number;
  failed: number;
  processing: number;
  pending: number;
  tasks: BatchTaskResponse[];
};
