import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import DownloadPage from "@/pages/DownloadPage.vue";
import { useResultStore } from "@/stores/result";

describe("DownloadPage", () => {
  it("shows message when final.mp4 is missing", async () => {
    setActivePinia(createPinia());
    const result = useResultStore();
    result.manifest = {
      task_id: "t",
      has_video: false,
      subtitle_languages: [],
      available_files: [],
      warnings: [],
    };
    result.loading = false;
    result.error = null;
    vi.spyOn(result, "fetchManifest").mockResolvedValue(result.manifest);

    const wrapper = mount(DownloadPage, {
      props: { taskId: "t" },
      global: {
        stubs: { RouterLink: true },
      },
    });

    await Promise.resolve();
    expect(wrapper.text()).toContain("final.mp4 不存在");
  });
});
