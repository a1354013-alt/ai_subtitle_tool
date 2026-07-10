import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

vi.mock("@/api/subtitles", () => ({
  getSubtitle: vi.fn(),
  updateSubtitle: vi.fn(),
}));

import { getSubtitle, updateSubtitle } from "@/api/subtitles";
import { useSubtitleStore } from "@/stores/subtitle";

describe("useSubtitleStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("stores update warnings and message after save succeeds", async () => {
    const store = useSubtitleStore();
    (updateSubtitle as unknown as any).mockResolvedValueOnce({
      status: "updated",
      format: "srt",
      language: "English",
      message: "Saved subtitle.",
      warnings: ["Final video was deleted."],
    });

    await store.updateSubtitle("task-1", "English", "srt", "1\n00:00:00,000 --> 00:00:01,000\nhello\n");

    expect(store.warnings).toEqual(["Final video was deleted."]);
    expect(store.lastUpdateMessage).toBe("Saved subtitle.");
    expect(store.isDirty).toBe(false);
    expect(store.lastSavedAt).toEqual(expect.any(Number));
  });

  it("resets update warnings when switching tasks", () => {
    const store = useSubtitleStore();
    store.taskId = "task-1";
    store.warnings = ["old warning"];
    store.lastUpdateMessage = "old message";

    store.resetForTask("task-2");

    expect(store.warnings).toEqual([]);
    expect(store.lastUpdateMessage).toBe("");
  });

  it("resets update warnings when fetching another subtitle", async () => {
    const store = useSubtitleStore();
    store.warnings = ["old warning"];
    store.lastUpdateMessage = "old message";
    (getSubtitle as unknown as any).mockResolvedValueOnce({
      content: "new content",
      format: "ass",
      filename: "task-1_English.ass",
    });

    await store.fetchSubtitle("task-1", "English", "ass");

    expect(store.warnings).toEqual([]);
    expect(store.lastUpdateMessage).toBe("");
    expect(store.content).toBe("new content");
  });
});
