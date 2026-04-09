import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import DownloadPage from "@/pages/DownloadPage.vue";
import { useResultStore } from "@/stores/result";

function flush() {
  return Promise.resolve();
}

describe("DownloadPage", () => {
  it("shows a clear note when final.mp4 is missing", async () => {
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
      global: { stubs: { RouterLink: true } },
    });

    await flush();
    expect(wrapper.text()).toContain("final.mp4 is missing");
  });

  it("renders EmptyState when manifest is null", async () => {
    setActivePinia(createPinia());
    const result = useResultStore();
    result.manifest = null;
    result.loading = false;
    result.error = null;
    vi.spyOn(result, "fetchManifest").mockResolvedValue(null as any);

    const wrapper = mount(DownloadPage, {
      props: { taskId: "t" },
      global: { stubs: { RouterLink: true } },
    });

    await flush();
    expect(wrapper.text()).toContain("No manifest");
  });

  it("shows Results not ready when manifest.task_status is not SUCCESS", async () => {
    setActivePinia(createPinia());
    const result = useResultStore();
    result.manifest = {
      task_id: "t",
      task_status: "PROCESSING",
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
      global: { stubs: { RouterLink: true } },
    });

    await flush();
    expect(wrapper.text()).toContain("Results not ready");
  });
});
