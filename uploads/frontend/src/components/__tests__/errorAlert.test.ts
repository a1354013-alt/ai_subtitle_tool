import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import ErrorAlert from "@/components/ErrorAlert.vue";

describe("ErrorAlert", () => {
  it("updates when props.error changes", async () => {
    const wrapper = mount(ErrorAlert, {
      props: { error: { message: "first", status: 500, detail: "d1" } },
    });

    expect(wrapper.text()).toContain("first");
    expect(wrapper.text()).toContain("d1");

    await wrapper.setProps({ error: { message: "second", status: 400, detail: "d2" } });

    expect(wrapper.text()).toContain("second");
    expect(wrapper.text()).toContain("d2");
  });
});
