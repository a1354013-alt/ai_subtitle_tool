import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import SubtitlePage from "@/pages/SubtitlePage.vue";
import { useResultStore } from "@/stores/result";
import { useSubtitleStore } from "@/stores/subtitle";

function flush() {
  return Promise.resolve();
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
});

