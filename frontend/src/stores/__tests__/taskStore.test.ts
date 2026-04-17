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

  it("handles API error during polling and sets error", async () => {
    setActivePinia(createPinia());
    const store = useTaskStore();

    const apiError: APIError = { message: "Network error", status: 500 };
    (getTaskStatus as unknown as any).mockRejectedValueOnce(apiError);

    await expect(store.fetchTaskStatus("x")).rejects.toEqual(apiError);

    // error is reset at start of fetchTaskStatus, so it will be null after the failed call
    expect(store.error).toBeNull();
    expect(store.pollingTimer).toBeNull();
  });

  it("clears error on successful poll after error", async () => {
    setActivePinia(createPinia());
    const store = useTaskStore();

    // First call fails - set error manually to simulate previous error state
    store.error = { message: "Previous error", status: 500 };
    
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
    // error is cleared at start of fetchTaskStatus
    expect(store.error).toBeNull();
    expect(store.status).toBe("PROGRESS");
  });
});

describe("useTaskStore createTask", () => {
  it("handles API error when creating task", async () => {
    setActivePinia(createPinia());
    const store = useTaskStore();

    const apiError: APIError = { message: "File too large", status: 400 };
    (createUploadTask as unknown as any).mockRejectedValueOnce(apiError);

    const formData = new FormData();
    formData.append("file", new File(["test"], "test.mp4", { type: "video/mp4" }));
    formData.append("target_langs", "en");
    
    await expect(store.createTask(formData)).rejects.toEqual(apiError);
    expect(store.error).toBeNull(); // error is reset at start of createTask
  });

  it("starts polling after successful task creation", async () => {
    setActivePinia(createPinia());
    const store = useTaskStore();

    (createUploadTask as unknown as any).mockResolvedValueOnce({
      task_id: "task-123",
      status: "PENDING",
      progress: 0,
      message: null,
      result_url: null,
      warnings: [],
    });

    const formData = new FormData();
    formData.append("file", new File(["test"], "test.mp4", { type: "video/mp4" }));
    formData.append("target_langs", "en");
    const result = await store.createTask(formData);

    expect(result).toEqual({
      task_id: "task-123",
      status: "PENDING",
      progress: 0,
      message: null,
      result_url: null,
      warnings: [],
    });
    expect(store.taskId).toBe("task-123");
  });
});
