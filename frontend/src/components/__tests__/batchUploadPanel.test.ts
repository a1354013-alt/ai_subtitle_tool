import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BatchUploadPanel from "@/components/BatchUploadPanel.vue";
import type { BatchStatusResponse } from "@/types/api";

const {
  mockUploadBatch,
  mockGetBatchStatus,
  mockDownloadBatch,
  mockGetAppConfig,
  mockGetAppCapabilities,
} = vi.hoisted(() => ({
  mockUploadBatch: vi.fn(),
  mockGetBatchStatus: vi.fn(),
  mockDownloadBatch: vi.fn((batchId: string) => `/batch/${batchId}/download`),
  mockGetAppConfig: vi.fn(),
  mockGetAppCapabilities: vi.fn(),
}));

vi.mock("@/api/batch", () => ({
  uploadBatch: mockUploadBatch,
  getBatchStatus: mockGetBatchStatus,
  downloadBatch: mockDownloadBatch,
}));

vi.mock("@/api/config", () => ({
  getAppConfig: mockGetAppConfig,
}));

vi.mock("@/api/capabilities", () => ({
  getAppCapabilities: mockGetAppCapabilities,
}));

function makeBatchStatus(status: string): BatchStatusResponse {
  return {
    batch_id: "batch-123",
    total: 1,
    completed: status === "SUCCESS" ? 1 : 0,
    failed: ["FAILURE", "CANCELED"].includes(status) ? 1 : 0,
    processing: status === "PROCESSING" ? 1 : 0,
    pending: status === "PENDING" ? 1 : 0,
    tasks: [
      {
        task_id: "task-1",
        filename: "demo.mp4",
        status,
        progress: status === "SUCCESS" ? 100 : 25,
        error: ["FAILURE", "CANCELED"].includes(status) ? "Boom" : null,
        download_urls:
          status === "SUCCESS"
            ? {
                video: "/download/task-1",
                subtitles: {
                  English: {
                    srt: "/download/task-1?lang=English&format=srt",
                    ass: "/download/task-1?lang=English&format=ass",
                    vtt: "/download/task-1?lang=English&format=vtt",
                  },
                },
              }
            : null,
      },
    ],
  };
}

async function mountPanel() {
  mockGetAppConfig.mockResolvedValue({
    maxUploadSizeMb: 2048,
    maxBatchFiles: 20,
    supportedExtensions: [".mp4", ".mkv", ".avi", ".mov"],
    batchUploadEnabled: true,
    subtitleFormats: ["srt", "ass", "vtt"],
    translationEnabled: false,
    openaiConfigured: false,
    defaultTargetLanguage: "Original",
    availableModes: ["transcribe"],
    provider: "none",
    model: null,
    reason: "translation_disabled",
    message: null,
  });
  mockGetAppCapabilities.mockResolvedValue({
    provider: "none",
    model: null,
    translationEnabled: false,
    reason: "translation_disabled",
    message: null,
    defaultTargetLanguage: "Original",
    availableModes: ["transcribe"],
    openaiConfigured: false,
  });
  const wrapper = mount(BatchUploadPanel);
  await flushPromises();
  return wrapper;
}

async function submitBatchWithStatus(status: string) {
  mockUploadBatch.mockResolvedValueOnce({ batch_id: "batch-123", tasks: [] });
  mockGetBatchStatus.mockResolvedValueOnce(makeBatchStatus(status));

  const wrapper = await mountPanel();
  const input = wrapper.get('input[type="file"]');
  Object.defineProperty(input.element, "files", {
    configurable: true,
    value: [new File(["video"], "demo.mp4", { type: "video/mp4" })],
  });
  await input.trigger("change");
  await wrapper.get("form").trigger("submit.prevent");
  await flushPromises();
  return wrapper;
}

describe("BatchUploadPanel", () => {
  beforeEach(() => {
    mockUploadBatch.mockReset();
    mockGetBatchStatus.mockReset();
    mockDownloadBatch.mockReset();
    mockGetAppConfig.mockReset();
    mockGetAppCapabilities.mockReset();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  it("shows download buttons for SUCCESS and uses same-origin batch URLs by default", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");

    const wrapper = await submitBatchWithStatus("SUCCESS");

    expect(wrapper.text()).toContain("Completed");
    const links = wrapper.findAll(".task-actions a");
    expect(links).toHaveLength(4);
    expect(links[0].attributes("href")).toBe("/download/task-1");
    expect(links[1].attributes("href")).toBe("/download/task-1?lang=English&format=srt");
    expect(links[2].attributes("href")).toBe("/download/task-1?lang=English&format=ass");
    expect(links[3].attributes("href")).toBe("/download/task-1?lang=English&format=vtt");
  });

  it("uses configured API base URL for SUCCESS download buttons", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "http://127.0.0.1:8891");

    const wrapper = await submitBatchWithStatus("SUCCESS");

    const links = wrapper.findAll(".task-actions a");
    expect(links).toHaveLength(4);
    expect(links[0].attributes("href")).toBe("http://127.0.0.1:8891/download/task-1");
    expect(links[1].attributes("href")).toBe("http://127.0.0.1:8891/download/task-1?lang=English&format=srt");
    expect(links[2].attributes("href")).toBe("http://127.0.0.1:8891/download/task-1?lang=English&format=ass");
    expect(links[3].attributes("href")).toBe("http://127.0.0.1:8891/download/task-1?lang=English&format=vtt");
  });

  it("shows failed styling for FAILURE", async () => {
    const failureWrapper = await submitBatchWithStatus("FAILURE");
    expect(failureWrapper.text()).toContain("Failed");
    expect(failureWrapper.find(".task-status .text-danger").exists()).toBe(true);
    expect(failureWrapper.text()).toContain("Boom");
  });

  it("validates unsupported files before upload", async () => {
    const wrapper = await mountPanel();
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["video"], "demo.txt", { type: "text/plain" })],
    });

    await input.trigger("change");
    await flushPromises();

    expect(wrapper.text()).toContain("Unsupported file format");
    expect(mockUploadBatch).not.toHaveBeenCalled();
  });

  it("submits Original when translation is unavailable", async () => {
    mockUploadBatch.mockResolvedValueOnce({ batch_id: "batch-123", tasks: [] });
    mockGetBatchStatus.mockResolvedValueOnce(makeBatchStatus("PENDING"));

    const wrapper = await mountPanel();
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["video"], "demo.mp4", { type: "video/mp4" })],
    });
    await input.trigger("change");
    await wrapper.get("form").trigger("submit.prevent");
    await flushPromises();

    const payload = mockUploadBatch.mock.calls[0][0] as FormData;
    expect(payload.get("target_langs")).toBe("Original");
  });

  it("submits remove_silence option for batch uploads", async () => {
    mockUploadBatch.mockResolvedValueOnce({ batch_id: "batch-123", tasks: [] });
    mockGetBatchStatus.mockResolvedValueOnce(makeBatchStatus("PENDING"));

    const wrapper = await mountPanel();
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["video"], "demo.mp4", { type: "video/mp4" })],
    });
    await input.trigger("change");

    const checkbox = wrapper.findAll('input[type="checkbox"]').at(1);
    expect(checkbox).toBeTruthy();
    await checkbox!.setValue(true);
    await wrapper.get("form").trigger("submit.prevent");
    await flushPromises();

    const payload = mockUploadBatch.mock.calls[0][0] as FormData;
    expect(payload.get("remove_silence")).toBe("true");
  });

  it("shows Ollama status instead of hardcoded OpenAI key warning", async () => {
    mockGetAppCapabilities.mockResolvedValueOnce({
      provider: "ollama",
      model: "gemma3:12b",
      translationEnabled: true,
      reason: null,
      message: null,
      defaultTargetLanguage: "Traditional Chinese",
      availableModes: ["transcribe", "translate"],
      openaiConfigured: false,
    });

    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain("Ollama");
    expect(wrapper.text()).toContain("gemma3:12b");
    expect(wrapper.text()).not.toContain("OpenAI API Key");
  });
});
