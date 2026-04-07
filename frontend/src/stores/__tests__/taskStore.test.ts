import { describe, expect, it, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("@/api/tasks", () => {
  return {
    createUploadTask: vi.fn(),
    getTaskStatus: vi.fn(),
  };
});

import { getTaskStatus } from "@/api/tasks";
import { useTaskStore } from "@/stores/task";

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
});
