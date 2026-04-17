import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("@/api/tasks", () => {
  return {
    createUploadTask: vi.fn(),
    getTaskStatus: vi.fn(),
  };
});

import { getTaskStatus, createUploadTask } from "@/api/tasks";
import { useTaskStore } from "@/stores/task";
import { usePreferencesStore } from "@/stores/preferences";
import type { APIError } from "@/types/api";

describe("useTaskStore polling", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("stops polling on terminal status (SUCCESS)", async () => {
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

  it("stores API error during polling without crashing the polling loop", async () => {
    const store = useTaskStore();
    const apiError: APIError = { message: "Network error", status: 500 };
    (getTaskStatus as unknown as any).mockRejectedValueOnce(apiError);

    await store.startPolling("x");

    expect(store.error).toEqual(apiError);
    expect(store.pollingTimer).not.toBeNull();
  });

  it("clears previous error on successful poll", async () => {
    const store = useTaskStore();
    store.error = { message: "Temporary error", status: 503 };

    (getTaskStatus as unknown as any).mockResolvedValueOnce({
      task_id: "x",
      status: "PROCESSING",
      progress: 50,
      message: null,
      result_url: null,
      warnings: [],
    });

    await store.fetchTaskStatus("x");

    expect(store.error).toBeNull();
    expect(store.status).toBe("PROCESSING");
    expect(store.progress).toBe(50);
  });

  it("stops polling when an interval poll reaches terminal status", async () => {
    const store = useTaskStore();

    (getTaskStatus as unknown as any)
      .mockResolvedValueOnce({
        task_id: "x",
        status: "PROCESSING",
        progress: 10,
        message: null,
        result_url: null,
        warnings: [],
      })
      .mockResolvedValueOnce({
        task_id: "x",
        status: "SUCCESS",
        progress: 100,
        message: null,
        result_url: null,
        warnings: [],
      });

    await store.startPolling("x");
    expect(store.pollingTimer).not.toBeNull();

    await vi.advanceTimersByTimeAsync(1000);

    expect(store.status).toBe("SUCCESS");
    expect(store.pollingTimer).toBeNull();
  });
});

describe("useTaskStore createTask", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates task from FormData and stores backend response", async () => {
    const store = useTaskStore();
    const prefs = usePreferencesStore();

    (createUploadTask as unknown as any).mockResolvedValueOnce({
      task_id: "task-123",
      status: "PENDING",
      progress: 0,
      message: null,
      result_url: null,
      warnings: [],
    });

    const fd = new FormData();
    fd.append("file", new File(["test"], "test.mp4", { type: "video/mp4" }));
    fd.append("target_langs", "en,ja");

    const result = await store.createTask(fd);

    expect(result.task_id).toBe("task-123");
    expect(store.taskId).toBe("task-123");
    expect(store.status).toBe("PENDING");
    expect(store.error).toBeNull();
    expect(prefs.preferredLang).toBe("en");
  });

  it("propagates API error when creating task", async () => {
    const store = useTaskStore();
    const apiError: APIError = { message: "File too large", status: 400 };
    (createUploadTask as unknown as any).mockRejectedValueOnce(apiError);

    const fd = new FormData();
    fd.append("file", new File(["test"], "test.mp4", { type: "video/mp4" }));
    fd.append("target_langs", "en");

    await expect(store.createTask(fd)).rejects.toEqual(apiError);
    expect(store.error).toBeNull();
  });
});