import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import SubtitlePage from "@/pages/SubtitlePage.vue";
import { useResultStore } from "@/stores/result";
import { useSubtitleStore } from "@/stores/subtitle";

function flush() {
  return Promise.resolve();
}

function seedManifest() {
  const result = useResultStore();
  result.manifest = {
    task_id: "t",
    has_video: true,
    subtitle_languages: ["Traditional_Chinese", "English"],
    available_files: [
      { lang: "Traditional_Chinese", display_name: "Traditional Chinese", ass: true, srt: true },
      { lang: "English", display_name: "English", ass: true, srt: true },
    ],
    warnings: [],
  };
  vi.spyOn(result, "fetchManifest").mockResolvedValue(result.manifest);
  return result;
}

describe("SubtitlePage", () => {
  it("fetches once on mount, and once per lang/format switch", async () => {
    setActivePinia(createPinia());
    seedManifest();

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

    await flush();
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    const langSelect = wrapper.find("select.select");
    await langSelect.setValue("English");
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(fetchSpy.mock.calls.at(-1)?.[1]).toBe("English");

    const buttons = wrapper.findAll("button.tab");
    expect(buttons.length).toBe(2);
    await buttons[1].trigger("click");
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    expect(fetchSpy.mock.calls.at(-1)?.[2]).toBe("srt");
  });

  it("does not switch lang/format when dirty and confirm is cancelled", async () => {
    setActivePinia(createPinia());
    seedManifest();

    const sub = useSubtitleStore();
    const fetchSpy = vi.spyOn(sub, "fetchSubtitle").mockResolvedValue({
      content: "x",
      format: "ass",
      filename: "t_Traditional_Chinese.ass",
    } as any);

    vi.spyOn(window, "confirm").mockReturnValue(false);

    const wrapper = mount(SubtitlePage, {
      props: { taskId: "t" },
      global: { stubs: { RouterLink: true } },
    });

    await flush();
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // user edits content -> dirty
    sub.setContent("edited");

    // attempt switch language (cancel)
    const langSelect = wrapper.find("select.select");
    await langSelect.setValue("English");
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(sub.lang).toBe("Traditional_Chinese");

    // attempt switch format (cancel)
    const buttons = wrapper.findAll("button.tab");
    await buttons[1].trigger("click");
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(sub.format).toBe("ass");
  });
});
