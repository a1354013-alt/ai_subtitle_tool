import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import HomePage from "@/pages/HomePage.vue";
import UploadForm from "@/components/UploadForm.vue";

describe("smoke", () => {
  it("alias import works", async () => {
    const mod = await import("@/api/client");
    expect(typeof mod.buildApiUrl).toBe("function");
  });

  it("HomePage renders", () => {
    const wrapper = mount(HomePage, {
      global: {
        stubs: { RouterLink: true },
      },
    });
    expect(wrapper.text()).toContain("上傳影片");
  });

  it("UploadForm renders", () => {
    const wrapper = mount(UploadForm, { props: { submitting: false } });
    expect(wrapper.text()).toContain("建立任務");
  });
});

