import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import SubtitlePage from "@/pages/SubtitlePage.vue";
import { useResultStore } from "@/stores/result";
import { useSubtitleStore } from "@/stores/subtitle";

const { mockRebuildFinalVideo } = vi.hoisted(() => ({
  mockRebuildFinalVideo: vi.fn(),
}));

vi.mock("@/api/tasks", () => ({
  rebuildFinalVideo: mockRebuildFinalVideo,
}));

function flush() {
  return flushPromises();
}

function seedManifest(partial?: Partial<ReturnType<typeof useResultStore>["manifest"]>) {
  const result = useResultStore();
  result.manifest = {
    task_id: "t",
    task_status: "SUCCESS",
    has_video: true,
    subtitle_languages: ["Traditional_Chinese", "English"],
    available_files: [
      { lang: "Traditional_Chinese", display_name: "Traditional Chinese", ass: true, srt: true },
      { lang: "English", display_name: "English", ass: true, srt: true },
    ],
    warnings: [],
    ...(partial ?? {}),
  };
  vi.spyOn(result, "fetchManifest").mockResolvedValue(result.manifest);
  return result;
}

async function mountViaRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/task/:taskId/subtitles", name: "subtitles", component: SubtitlePage, props: true },
      { path: "/task/:taskId/downloads", name: "downloads", component: { template: "<div>downloads</div>" }, props: true },
      { path: "/task/:taskId", name: "task", component: { template: "<div>task</div>" }, props: true },
    ],
  });

  await router.push("/task/t/subtitles");
  await router.isReady();

  const wrapper = mount({ template: "<router-view />" }, { global: { plugins: [router] } });
  await flush();
  await flush();
  return { router, wrapper };
}

describe("SubtitlePage", () => {
  it("initializes format from manifest (srt-only task uses srt), then fetches per lang/format switch", async () => {
    setActivePinia(createPinia());
    seedManifest({
      available_files: [
        { lang: "Traditional_Chinese", display_name: "Traditional Chinese", ass: false, srt: true },
        { lang: "English", display_name: "English", ass: true, srt: true },
      ],
    });

    const sub = useSubtitleStore();
    const fetchSpy = vi.spyOn(sub, "fetchSubtitle").mockImplementation(async (_taskId, lang, format) => {
      sub.lang = lang;
      sub.format = format;
      sub.content = "x";
      sub.isDirty = false;
      return { content: "x" } as any;
    });

    const { wrapper } = await mountViaRouter();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0]?.[2]).toBe("srt");

    // language switch -> fetch again
    const langSelect = wrapper.find("select.select");
    await langSelect.setValue("English");
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(fetchSpy.mock.calls.at(-1)?.[1]).toBe("English");

    // format switch to ASS then back to SRT -> fetch twice
    const buttons = wrapper.findAll("button.tab");
    await buttons[0].trigger("click"); // ass
    await flush();
    await buttons[1].trigger("click"); // srt
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(4);
    expect(fetchSpy.mock.calls.at(-1)?.[2]).toBe("srt");
  });

  it("does not switch lang/format when dirty and confirm is cancelled", async () => {
    setActivePinia(createPinia());
    seedManifest();

    const sub = useSubtitleStore();
    const fetchSpy = vi.spyOn(sub, "fetchSubtitle").mockImplementation(async (_taskId, lang, format) => {
      sub.lang = lang;
      sub.format = format;
      sub.content = "x";
      sub.isDirty = false;
      return { content: "x" } as any;
    });

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    const { wrapper } = await mountViaRouter();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(sub.lang).toBe("Traditional_Chinese");

    sub.setContent("edited"); // dirty

    const langSelect = wrapper.find("select.select");
    await langSelect.setValue("English");
    await flush();
    expect(confirmSpy).toHaveBeenCalled();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(sub.lang).toBe("Traditional_Chinese");

    const buttons = wrapper.findAll("button.tab");
    await buttons[1].trigger("click"); // srt
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(sub.format).toBe("ass");
  });

  it("blocks route navigation when dirty (route guard)", async () => {
    setActivePinia(createPinia());
    seedManifest();

    const sub = useSubtitleStore();
    vi.spyOn(sub, "fetchSubtitle").mockImplementation(async (_taskId, lang, format) => {
      sub.lang = lang;
      sub.format = format;
      sub.content = "x";
      sub.isDirty = false;
      return { content: "x" } as any;
    });

    const { router } = await mountViaRouter();
    sub.setContent("edited"); // dirty
    vi.spyOn(window, "confirm").mockReturnValue(false);

    await router.push("/task/t/downloads");
    await flush();
    expect(router.currentRoute.value.name).toBe("subtitles");
  });

  it("does not fetch subtitle when manifest has no available_files", async () => {
    setActivePinia(createPinia());
    seedManifest({ available_files: [], subtitle_languages: [] });

    const sub = useSubtitleStore();
    const fetchSpy = vi.spyOn(sub, "fetchSubtitle").mockImplementation(async () => {
      throw new Error("should not be called");
    });

    const { wrapper } = await mountViaRouter();
    expect(fetchSpy).toHaveBeenCalledTimes(0);
    expect(wrapper.text()).toContain("No subtitles available");
  });

  it("does not switch to an unavailable format for the current language", async () => {
    setActivePinia(createPinia());
    seedManifest({
      available_files: [{ lang: "Traditional_Chinese", display_name: "Traditional Chinese", ass: true, srt: false }],
      subtitle_languages: ["Traditional_Chinese"],
    });

    const sub = useSubtitleStore();
    const fetchSpy = vi.spyOn(sub, "fetchSubtitle").mockImplementation(async (_taskId, lang, format) => {
      sub.lang = lang;
      sub.format = format;
      sub.content = "x";
      sub.isDirty = false;
      return { content: "x" } as any;
    });

    vi.spyOn(window, "alert").mockImplementation(() => {});

    const { wrapper } = await mountViaRouter();
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    const buttons = wrapper.findAll("button.tab");
    await buttons[1].trigger("click"); // switch to srt
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(window.alert).toHaveBeenCalled();
  });

  it("shows backend warnings and rebuild action after subtitle save", async () => {
    setActivePinia(createPinia());
    seedManifest();

    const sub = useSubtitleStore();
    vi.spyOn(sub, "fetchSubtitle").mockImplementation(async (_taskId, lang, format) => {
      sub.lang = lang;
      sub.format = format;
      sub.content = "1\n00:00:00,000 --> 00:00:01,000\nhello\n";
      sub.isDirty = false;
      return { content: sub.content } as any;
    });
    vi.spyOn(sub, "updateSubtitle").mockImplementation(async (_taskId, _lang, _format, content) => {
      sub.content = content;
      sub.isDirty = false;
      sub.lastSavedAt = Date.now();
      sub.lastUpdateMessage = "Successfully updated SRT subtitle for English.";
      sub.warnings = ["Final video was deleted to prevent using old subtitles."];
    });

    const { wrapper } = await mountViaRouter();
    sub.setContent("1\n00:00:00,000 --> 00:00:01,000\nedited\n");
    await flush();

    const saveButton = wrapper.findAll("button").find((button) => button.text() === "Save");
    await saveButton!.trigger("click");
    await flush();

    expect(wrapper.text()).toContain("Successfully updated SRT subtitle");
    expect(wrapper.text()).toContain("Final video was deleted");
    expect(wrapper.text()).toContain("Rebuild final video");
  });

  it("clicking rebuild calls API and navigates to rebuild task", async () => {
    setActivePinia(createPinia());
    seedManifest();
    const rebuildTaskId = "66666666-6666-6666-6666-666666666666";

    const sub = useSubtitleStore();
    vi.spyOn(sub, "fetchSubtitle").mockImplementation(async (_taskId, lang, format) => {
      sub.lang = lang;
      sub.format = format;
      sub.content = "1\n00:00:00,000 --> 00:00:01,000\nhello\n";
      sub.isDirty = false;
      return { content: sub.content } as any;
    });
    vi.spyOn(sub, "updateSubtitle").mockImplementation(async (_taskId, _lang, _format, content) => {
      sub.content = content;
      sub.isDirty = false;
      sub.lastSavedAt = Date.now();
      sub.lastUpdateMessage = "Saved.";
      sub.warnings = [];
    });
    mockRebuildFinalVideo.mockResolvedValueOnce({
      status: "queued",
      task_id: "t",
      rebuild_task_id: rebuildTaskId,
    });

    const { router, wrapper } = await mountViaRouter();
    sub.setContent("1\n00:00:00,000 --> 00:00:01,000\nedited\n");
    await flush();
    await wrapper.findAll("button").find((button) => button.text() === "Save")!.trigger("click");
    await flush();

    const rebuildButton = wrapper.findAll("button").find((button) => button.text() === "Rebuild final video");
    await rebuildButton!.trigger("click");
    await flush();

    expect(mockRebuildFinalVideo).toHaveBeenCalledWith("t", "Traditional_Chinese", "ass");
    expect(router.currentRoute.value.name).toBe("task");
    expect(router.currentRoute.value.params.taskId).toBe(rebuildTaskId);
  });
});
