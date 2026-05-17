import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";

const { mockRebuildFinalVideo } = vi.hoisted(() => ({
  mockRebuildFinalVideo: vi.fn(),
}));

vi.mock("@/api/tasks", () => ({
  rebuildFinalVideo: mockRebuildFinalVideo,
}));

vi.mock("vue-router", async () => {
  const actual = await vi.importActual<any>("vue-router");
  return {
    ...actual,
    useRouter: () => ({ push: vi.fn() }),
  };
});

import DownloadPage from "@/pages/DownloadPage.vue";
import { useResultStore } from "@/stores/result";

function flush() {
  return flushPromises();
}

describe("DownloadPage", () => {
  beforeEach(() => {
    mockRebuildFinalVideo.mockReset();
  });

  it("shows a clear note when final.mp4 is missing", async () => {
    setActivePinia(createPinia());
    const result = useResultStore();
    result.manifest = {
      task_id: "t",
      task_status: "SUCCESS",
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

  it("shows translation fallback warnings", async () => {
    setActivePinia(createPinia());
    const result = useResultStore();
    result.manifest = {
      task_id: "t",
      task_status: "SUCCESS",
      has_video: true,
      subtitle_languages: ["English"],
      available_files: [
        {
          lang: "English",
          display_name: "English",
          ass: false,
          srt: true,
          translated: false,
          fallback_reason: "translation provider unavailable",
        },
      ],
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
    expect(wrapper.text()).toContain("Translation warnings");
    expect(wrapper.text()).toContain("translation provider unavailable");
    expect(wrapper.text()).toContain("this subtitle uses original text");
  });

  it("shows rebuild failure errors", async () => {
    setActivePinia(createPinia());
    localStorage.setItem("ai_subtitle_tool_preferred_lang", "English");
    const result = useResultStore();
    result.manifest = {
      task_id: "t",
      task_status: "SUCCESS",
      has_video: false,
      subtitle_languages: ["English"],
      available_files: [{ lang: "English", display_name: "English", ass: false, srt: true, translated: true }],
      warnings: [],
    };
    result.loading = false;
    result.error = null;
    vi.spyOn(result, "fetchManifest").mockResolvedValue(result.manifest);
    mockRebuildFinalVideo.mockRejectedValueOnce({ message: "Rebuild failed", status: 500 });

    const wrapper = mount(DownloadPage, {
      props: { taskId: "t" },
      global: { stubs: { RouterLink: true } },
    });

    await flush();
    const rebuildButton = wrapper.findAll("button").find((button) => button.text().includes("editor.rebuild"));
    expect(rebuildButton).toBeTruthy();
    await rebuildButton!.trigger("click");
    await flush();

    expect(mockRebuildFinalVideo).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain("Rebuild failed");
  });
});
