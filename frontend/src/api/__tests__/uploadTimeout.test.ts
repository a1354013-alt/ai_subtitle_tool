import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockApiRequest } = vi.hoisted(() => ({
  mockApiRequest: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiRequest: mockApiRequest,
  buildApiUrl: (path: string) => path,
  UPLOAD_TIMEOUT_MS: 0,
}));

describe("upload API timeouts", () => {
  beforeEach(() => {
    mockApiRequest.mockReset();
  });

  it("disables the short default timeout for single video upload", async () => {
    const { createUploadTask } = await import("@/api/tasks");
    const formData = new FormData();

    await createUploadTask(formData);

    expect(mockApiRequest).toHaveBeenCalledWith("/upload", expect.objectContaining({
      method: "POST",
      body: formData,
      timeoutMs: 0,
      timeoutMessage: "Upload timeout",
    }));
  });

  it("disables the short default timeout for batch upload", async () => {
    const { uploadBatch } = await import("@/api/batch");
    const formData = new FormData();

    await uploadBatch(formData);

    expect(mockApiRequest).toHaveBeenCalledWith("/batch/upload", expect.objectContaining({
      method: "POST",
      body: formData,
      timeoutMs: 0,
      timeoutMessage: "Upload timeout",
    }));
  });
});
