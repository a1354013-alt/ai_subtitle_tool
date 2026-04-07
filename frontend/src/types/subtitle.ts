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

