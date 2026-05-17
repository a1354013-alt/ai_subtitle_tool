import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import UploadForm from "@/components/UploadForm.vue";

const { mockGetAppConfig } = vi.hoisted(() => ({
  mockGetAppConfig: vi.fn(),
}));

vi.mock("@/api/config", () => ({
  getAppConfig: mockGetAppConfig,
}));

describe("UploadForm", () => {
  beforeEach(() => {
    mockGetAppConfig.mockReset();
    mockGetAppConfig.mockResolvedValue({
      maxUploadSizeMb: 1,
      maxBatchFiles: 20,
      supportedExtensions: [".mp4"],
      batchUploadEnabled: true,
      subtitleFormats: ["srt", "ass", "vtt"],
    });
  });

  it("uses backend config for single-file upload size validation", async () => {
    const wrapper = mount(UploadForm, { props: { submitting: false } });
    await flushPromises();

    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File([new Uint8Array(2 * 1024 * 1024)], "large.mp4", { type: "video/mp4" })],
    });
    await input.trigger("change");

    expect(wrapper.text()).toContain("large.mp4 exceeds the 1MB upload limit");
    expect(wrapper.emitted("submit")).toBeUndefined();
  });
});
