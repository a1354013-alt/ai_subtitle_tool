export type SubtitleFormat = "ass" | "srt";

export type SubtitleResponse = {
  content: string;
  format: SubtitleFormat;
  filename: string;
};

export type UpdateSubtitlePayload = {
  content: string;
  format: SubtitleFormat;
};

export type UpdateSubtitleResponse = {
  status: string;
  format: SubtitleFormat;
  language: string;
  message: string;
  warnings: string[];
};
