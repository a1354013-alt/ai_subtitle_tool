import { afterEach } from "vitest";
import { config } from "@vue/test-utils";

const messages: Record<string, string> = {
  "upload.title": "Upload Video",
  "upload.selectVideo": "Select Video File",
  "upload.generate": "Create task",
  "upload.targetLanguages": "Target Languages",
  "upload.subtitleFormat": "Subtitle Format",
  "upload.burnSubtitles": "Burn Subtitles",
  "upload.removeSilence": "Remove Silence",
  "upload.parallel": "Parallel",

  "task.status": "Task Status",
  "task.progress": "Progress",

  "editor.title": "Subtitle Editor",
  "editor.save": "Save",
  "editor.rebuild": "Rebuild",
  "editor.download": "Download Subtitles",

  "download.title": "Downloads",
  "download.button": "Download",

  "common.loading": "Loading...",
  "common.suggestion": "Suggestion",

  "navbar.home": "Home",
  "navbar.tasks": "Tasks",

  "batch.downloadZip": "Download Batch ZIP",
};

config.global.mocks = {
  ...(config.global.mocks ?? {}),
  $t: (key: string) => messages[key] ?? key,
};

afterEach(() => {
  localStorage.clear();
});