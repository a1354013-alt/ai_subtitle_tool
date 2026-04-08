export type FileInfo = {
  lang: string;
  display_name: string;
  ass: boolean;
  srt: boolean;
};

export type ResultsManifestResponse = {
  task_id: string;
  has_video: boolean;
  /**
   * Convenience list of languages included in the manifest.
   * Keep for backwards-compatibility; treat `available_files` as the primary source of truth.
   */
  subtitle_languages: string[];
  /**
   * Primary source of truth for available downloadable files per language.
   * UI should use this to drive language selection and download availability.
   */
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
