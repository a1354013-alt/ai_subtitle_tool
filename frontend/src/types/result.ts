export type FileInfo = {
  lang: string;
  display_name: string;
  ass: boolean;
  srt: boolean;
};

export type ResultsManifestResponse = {
  task_id: string;
  has_video: boolean;
  subtitle_languages: string[];
  available_files: FileInfo[];
  warnings: string[];
};

export type DownloadItem = {
  key: string;
  label: string;
  description?: string;
  available: boolean;
  url?: string;
};

