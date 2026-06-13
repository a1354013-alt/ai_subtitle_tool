import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import UploadForm from "@/components/UploadForm.vue";

const { mockGetAppConfig, mockGetAppCapabilities } = vi.hoisted(() => ({
  mockGetAppConfig: vi.fn(),
  mockGetAppCapabilities: vi.fn(),
}));

vi.mock("@/api/config", () => ({
  getAppConfig: mockGetAppConfig,
}));

vi.mock("@/api/capabilities", () => ({
  getAppCapabilities: mockGetAppCapabilities,
}));

describe("UploadForm", () => {
  beforeEach(() => {
    mockGetAppConfig.mockReset();
    mockGetAppCapabilities.mockReset();
    mockGetAppConfig.mockResolvedValue({
      maxUploadSizeMb: 1,
      maxBatchFiles: 20,
      supportedExtensions: [".mp4"],
      batchUploadEnabled: true,
      subtitleFormats: ["srt", "ass", "vtt"],
      translationEnabled: false,
      openaiConfigured: false,
      defaultTargetLanguage: "Original",
      availableModes: ["transcribe"],
      provider: "none",
      model: null,
      reason: "translation_disabled",
      message: null,
    });
    mockGetAppCapabilities.mockResolvedValue({
      provider: "none",
      model: null,
      translationEnabled: false,
      reason: "translation_disabled",
      message: null,
      defaultTargetLanguage: "Original",
      availableModes: ["transcribe"],
      openaiConfigured: false,
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

  it("submits Original when translation is unavailable", async () => {
    const wrapper = mount(UploadForm, { props: { submitting: false } });
    await flushPromises();

    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["video"], "demo.mp4", { type: "video/mp4" })],
    });
    await input.trigger("change");
    await wrapper.get("form").trigger("submit.prevent");

    const payload = wrapper.emitted("submit")?.[0]?.[0] as FormData;
    expect(payload.get("target_langs")).toBe("Original");
  });

  it("does not submit translation targets when Ollama is unavailable", async () => {
    mockGetAppCapabilities.mockResolvedValueOnce({
      provider: "ollama",
      model: "gemma3:12b",
      translationEnabled: false,
      reason: "ollama_unreachable",
      message: "Ollama is not reachable.",
      defaultTargetLanguage: "Original",
      availableModes: ["transcribe"],
      openaiConfigured: false,
    });

    const wrapper = mount(UploadForm, { props: { submitting: false } });
    await flushPromises();

    await wrapper.get('input[type="text"]').setValue("Traditional Chinese");
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["video"], "demo.mp4", { type: "video/mp4" })],
    });
    await input.trigger("change");
    await wrapper.get("form").trigger("submit.prevent");

    expect(wrapper.emitted("submit")).toBeUndefined();
    expect(wrapper.text()).toContain("Ollama");
    expect(wrapper.text()).not.toContain("OpenAI API Key");
  });
});
