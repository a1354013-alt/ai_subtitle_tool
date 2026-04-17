import { describe, expect, it, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("@/api/tasks", () => {
  return {
    createUploadTask: vi.fn(),
    getTaskStatus: vi.fn(),
  };
});

import { getTaskStatus, createUploadTask } from "@/api/tasks";
import { useTaskStore } from "@/stores/task";
import type { APIError } from "@/types/api";

describe("useTaskStore polling", () => {
  it("stops polling on terminal status (SUCCESS)", async () => {
    setActivePinia(createPinia());
    const store = useTaskStore();

    (getTaskStatus as unknown as any).mockResolvedValueOnce({
      task_id: "x",
      status: "SUCCESS",
      progress: 100,
      message: null,
      result_url: null,
      warnings: [],
    });

    const stopSpy = vi.spyOn(store, "stopPolling");
    await store.fetchTaskStatus("x");
    expect(stopSpy).toHaveBeenCalledOnce();
  });

  it("stops polling on terminal status (FAILURE/REVOKED)", async () => {
    setActivePinia(createPinia());
    const store = useTaskStore();

    const stopSpy = vi.spyOn(store, "stopPolling");

    (getTaskStatus as unknown as any).mockResolvedValueOnce({
      task_id: "x",
      status: "FAILURE",
      progress: 0,
      message: "boom",
      result_url: null,
      warnings: [],
    });
    await store.fetchTaskStatus("x");
    expect(stopSpy).toHaveBeenCalledTimes(1);

    (getTaskStatus as unknown as any).mockResolvedValueOnce({
      task_id: "x",
      status: "REVOKED",
      progress: 0,
      message: null,
      result_url: null,
      warnings: [],
    });
    await store.fetchTaskStatus("x");
    expect(stopSpy).toHaveBeenCalledTimes(2);
  });

  it("handles API error during polling and sets errorMessage", async () => {
    setActivePinia(createPinia());
    const store = useTaskStore();

    const apiError: APIError = { message: "Network error", status: 500 };
    (getTaskStatus as unknown as any).mockRejectedValueOnce(apiError);

    await store.fetchTaskStatus("x");

    expect(store.errorMessage).toBe("Network error");
    expect(store.isPolling).toBe(false);
  });

  it("clears errorMessage on successful poll after error", async () => {
    setActivePinia(createPinia());
    const store = useTaskStore();

    // First call fails
    (getTaskStatus as unknown as any).mockRejectedValueOnce({
      message: "Temporary error",
      status: 503,
    });
    await store.fetchTaskStatus("x");
    expect(store.errorMessage).toBe("Temporary error");

    // Second call succeeds
    (getTaskStatus as unknown as any).mockResolvedValueOnce({
      task_id: "x",
      status: "PROGRESS",
      progress: 50,
      message: null,
      result_url: null,
      warnings: [],
    });
    await store.fetchTaskStatus("x");
    expect(store.errorMessage).toBeNull();
    expect(store.isPolling).toBe(true);
  });
});

describe("useTaskStore createTask", () => {
  it("handles API error when creating task", async () => {
    setActivePinia(createPinia());
    const store = useTaskStore();

    const apiError: APIError = { message: "File too large", status: 400 };
    (createUploadTask as unknown as any).mockRejectedValueOnce(apiError);

    const file = new File(["test"], "test.mp4", { type: "video/mp4" });
    const result = await store.createTask(file, false, "en");

    expect(result).toBe(false);
    expect(store.errorMessage).toBe("File too large");
  });

  it("starts polling after successful task creation", async () => {
    setActivePinia(createPinia());
    const store = useTaskStore();

    (createUploadTask as unknown as any).mockResolvedValueOnce({
      task_id: "task-123",
    });

    const file = new File(["test"], "test.mp4", { type: "video/mp4" });
    const result = await store.createTask(file, false, "en");

    expect(result).toBe(true);
    expect(store.taskId).toBe("task-123");
    expect(store.isPolling).toBe(true);
  });
});
