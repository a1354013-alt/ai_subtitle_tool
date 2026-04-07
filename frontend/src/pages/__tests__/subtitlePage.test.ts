import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import SubtitlePage from "@/pages/SubtitlePage.vue";
import { useResultStore } from "@/stores/result";
import { useSubtitleStore } from "@/stores/subtitle";

describe("SubtitlePage", () => {
  it("can switch subtitle format (ass/srt)", async () => {
    setActivePinia(createPinia());

    const result = useResultStore();
    result.manifest = {
      task_id: "t",
      has_video: true,
      subtitle_languages: ["Traditional_Chinese"],
      available_files: [{ lang: "Traditional_Chinese", display_name: "Traditional Chinese", ass: true, srt: true }],
      warnings: [],
    };
    vi.spyOn(result, "fetchManifest").mockResolvedValue(result.manifest);

    const sub = useSubtitleStore();
    const fetchSpy = vi.spyOn(sub, "fetchSubtitle").mockResolvedValue({
      content: "x",
      format: "ass",
      filename: "t_Traditional_Chinese.ass",
    } as any);

    const wrapper = mount(SubtitlePage, {
      props: { taskId: "t" },
      global: { stubs: { RouterLink: true } },
    });

    await Promise.resolve();
    fetchSpy.mockClear();

    const buttons = wrapper.findAll("button.tab");
    expect(buttons.length).toBe(2);
    await buttons[1].trigger("click");

    expect(sub.format).toBe("srt");
    expect(fetchSpy).toHaveBeenCalled();
    const last = fetchSpy.mock.calls.at(-1);
    expect(last?.[0]).toBe("t");
    expect(last?.[1]).toBe("Traditional_Chinese");
    expect(last?.[2]).toBe("srt");
  });

  it("can switch subtitle language", async () => {
    setActivePinia(createPinia());

    const result = useResultStore();
    result.manifest = {
      task_id: "t",
      has_video: true,
      subtitle_languages: ["Traditional_Chinese", "English"],
      available_files: [
        { lang: "Traditional_Chinese", display_name: "Traditional Chinese", ass: true, srt: false },
        { lang: "English", display_name: "English", ass: true, srt: true },
      ],
      warnings: [],
    };
    vi.spyOn(result, "fetchManifest").mockResolvedValue(result.manifest);

    const sub = useSubtitleStore();
    sub.setLang("Traditional_Chinese");
    sub.markClean();
    const fetchSpy = vi.spyOn(sub, "fetchSubtitle").mockResolvedValue({
      content: "x",
      format: "ass",
      filename: "t_Traditional_Chinese.ass",
    } as any);

    const wrapper = mount(SubtitlePage, {
      props: { taskId: "t" },
      global: { stubs: { RouterLink: true } },
    });

    await Promise.resolve();
    fetchSpy.mockClear();

    const select = wrapper.find("select.select");
    expect(select.exists()).toBe(true);
    await select.setValue("English");

    expect(sub.lang).toBe("English");
    expect(fetchSpy).toHaveBeenCalled();
    const last = fetchSpy.mock.calls.at(-1);
    expect(last?.[0]).toBe("t");
    expect(last?.[1]).toBe("English");
  });
});

