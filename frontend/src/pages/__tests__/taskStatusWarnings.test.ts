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
    expect(wrapper.text()).toContain("Warnings");
    expect(wrapper.text()).toContain("a");
    expect(wrapper.text()).toContain("b");
  });
});
