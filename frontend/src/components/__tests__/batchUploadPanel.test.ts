import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BatchUploadPanel from "@/components/BatchUploadPanel.vue";
import type { BatchStatusResponse } from "@/types/api";

const {
  mockUploadBatch,
  mockGetBatchStatus,
  mockDownloadBatch,
  mockGetAppConfig,
} = vi.hoisted(() => ({
  mockUploadBatch: vi.fn(),
  mockGetBatchStatus: vi.fn(),
  mockDownloadBatch: vi.fn((batchId: string) => `/batch/${batchId}/download`),
  mockGetAppConfig: vi.fn(),
}));

vi.mock("@/api/batch", () => ({
  uploadBatch: mockUploadBatch,
  getBatchStatus: mockGetBatchStatus,
  downloadBatch: mockDownloadBatch,
}));

vi.mock("@/api/config", () => ({
  getAppConfig: mockGetAppConfig,
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
  });

  it("shows download buttons for SUCCESS and uses shared batch URLs", async () => {
    const wrapper = await submitBatchWithStatus("SUCCESS");

    expect(wrapper.text()).toContain("Completed");
    const links = wrapper.findAll(".task-actions a");
    expect(links).toHaveLength(4);
    expect(links[0].attributes("href")).toBe("/download/task-1");
    expect(links[1].attributes("href")).toBe("/download/task-1?lang=English&format=srt");
    expect(links[2].attributes("href")).toBe("/download/task-1?lang=English&format=ass");
    expect(links[3].attributes("href")).toBe("/download/task-1?lang=English&format=vtt");
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
});
