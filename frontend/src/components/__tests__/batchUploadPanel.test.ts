import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import axios from "axios";
import BatchUploadPanel from "@/components/BatchUploadPanel.vue";
import type { BatchStatusResponse } from "@/types/api";

vi.mock("axios", () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

const mockedAxios = axios as unknown as {
  post: ReturnType<typeof vi.fn>;
  get: ReturnType<typeof vi.fn>;
};

function makeBatchStatus(status: string): BatchStatusResponse {
  return {
    batch_id: "batch-123",
    total: 1,
    completed: status === "SUCCESS" ? 1 : 0,
    failed: status === "FAILURE" ? 1 : 0,
    processing: status === "PROCESSING" ? 1 : 0,
    pending: status === "PENDING" ? 1 : 0,
    tasks: [
      {
        task_id: "task-1",
        filename: "demo.mp4",
        status,
        progress: status === "SUCCESS" ? 100 : 25,
        error: ["FAILURE", "ERROR"].includes(status) ? "Boom" : null,
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

async function submitBatchWithStatus(status: string) {
  mockedAxios.post.mockResolvedValueOnce({ data: { batch_id: "batch-123" } });
  mockedAxios.get.mockResolvedValueOnce({ data: makeBatchStatus(status) });

  const wrapper = mount(BatchUploadPanel);
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
    mockedAxios.post.mockReset();
    mockedAxios.get.mockReset();
    vi.spyOn(window, "alert").mockImplementation(() => undefined);
  });

  it("shows download buttons for SUCCESS and uses /download URLs", async () => {
    const wrapper = await submitBatchWithStatus("SUCCESS");

    expect(wrapper.text()).toContain("Completed");
    const links = wrapper.findAll(".task-actions a");
    expect(links).toHaveLength(4);
    expect(links[0].attributes("href")).toBe("/download/task-1");
    expect(links[1].attributes("href")).toBe("/download/task-1?lang=English&format=srt");
    expect(links[2].attributes("href")).toBe("/download/task-1?lang=English&format=ass");
    expect(links[3].attributes("href")).toBe("/download/task-1?lang=English&format=vtt");
    expect(wrapper.html()).not.toContain("/results/task-1/download");
  });

  it("shows failed styling for FAILURE", async () => {
    const failureWrapper = await submitBatchWithStatus("FAILURE");
    expect(failureWrapper.text()).toContain("Failed");
    expect(failureWrapper.find(".task-status .text-danger").exists()).toBe(true);
    expect(failureWrapper.text()).toContain("Boom");
  });

  it("shows processing styling for PROCESSING and PENDING", async () => {
    const processingWrapper = await submitBatchWithStatus("PROCESSING");
    expect(processingWrapper.text()).toContain("Processing");
    expect(processingWrapper.find(".task-status .text-muted").exists()).toBe(true);

    const pendingWrapper = await submitBatchWithStatus("PENDING");
    expect(pendingWrapper.text()).toContain("Processing");
    expect(pendingWrapper.find(".task-status .text-muted").exists()).toBe(true);
  });
});
