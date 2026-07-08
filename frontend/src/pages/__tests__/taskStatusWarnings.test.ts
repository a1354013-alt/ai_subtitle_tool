import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import TaskStatusPage from "@/pages/TaskStatusPage.vue";
import { useTaskStore } from "@/stores/task";

describe("TaskStatusPage warnings", () => {
  it("renders warnings as a list when present", () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useTaskStore();
    store.$patch({
      taskId: "t",
      status: "PROCESSING",
      progress: 10,
      message: "working",
      warnings: ["a", "b"],
      error: null,
      pollingTimer: null,
    });

    vi.spyOn(store, "startPolling").mockResolvedValue(undefined as any);
    vi.spyOn(store, "stopPolling").mockImplementation(() => {});

    const wrapper = mount(TaskStatusPage, {
      props: { taskId: "t" },
      global: {
        plugins: [pinia],
        stubs: { RouterLink: true },
      },
    });

    const lis = wrapper.findAll("li");
    expect(lis.length).toBe(2);
    expect(wrapper.text()).toContain("Non-fatal warnings");
    expect(wrapper.text()).toContain("a");
    expect(wrapper.text()).toContain("b");
  });

  it("uses result_task_id for success action links when present", () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useTaskStore();
    store.$patch({
      taskId: "rebuild-task",
      status: "SUCCESS",
      progress: 100,
      message: "Completed",
      result_task_id: "original-task",
      result_url: "/results/original-task",
      warnings: [],
      error: null,
      pollingTimer: null,
    });

    vi.spyOn(store, "startPolling").mockResolvedValue(undefined as any);
    vi.spyOn(store, "stopPolling").mockImplementation(() => {});

    const wrapper = mount(TaskStatusPage, {
      props: { taskId: "rebuild-task" },
      global: {
        plugins: [pinia],
        stubs: { RouterLink: true },
      },
    });

    const links = wrapper.findAllComponents({ name: "RouterLink" });
    expect(links.at(1)?.props("to")).toEqual({ name: "subtitles", params: { taskId: "original-task" } });
    expect(links.at(2)?.props("to")).toEqual({ name: "downloads", params: { taskId: "original-task" } });
  });
});
