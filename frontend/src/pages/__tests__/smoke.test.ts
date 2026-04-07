import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import HomePage from "@/pages/HomePage.vue";
import UploadForm from "@/components/UploadForm.vue";

describe("smoke", () => {
  it("alias import works", async () => {
    const mod = await import("@/api/client");
    expect(typeof mod.buildApiUrl).toBe("function");
  });

  it("HomePage renders", () => {
    const pinia = createPinia();
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", name: "home", component: HomePage }],
    });
    const wrapper = mount(HomePage, {
      global: {
        plugins: [pinia, router],
      },
    });
    expect(wrapper.text()).toContain("上傳影片");
    expect(wrapper.find('input[type="file"]').exists()).toBe(true);
  });

  it("UploadForm renders", () => {
    const wrapper = mount(UploadForm, { props: { submitting: false } });
    expect(wrapper.text()).toContain("建立任務");
  });
});
