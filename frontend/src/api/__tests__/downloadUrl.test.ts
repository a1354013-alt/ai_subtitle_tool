import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/client", () => {
  return {
    apiRequest: vi.fn(),
    buildApiUrl: (path: string) => `http://api.example${path}`,
    buildQuery: (params: Record<string, string>) => {
      const qs = new URLSearchParams(params);
      const s = qs.toString();
      return s ? `?${s}` : "";
    },
  };
});

vi.mock("@/api/subtitles", () => {
  return {
    getPreferredLang: () => "English",
  };
});

describe("buildDownloadUrl", () => {
  it("uses the shared buildApiUrl() base URL logic", async () => {
    const { buildDownloadUrl } = await import("@/api/results");
    expect(buildDownloadUrl("abc")).toBe("http://api.example/download/abc");
  });

  it("includes lang+format when downloading subtitles", async () => {
    const { buildDownloadUrl } = await import("@/api/results");
    expect(buildDownloadUrl("abc", "ass", "Traditional_Chinese")).toBe(
      "http://api.example/download/abc?lang=Traditional_Chinese&format=ass"
    );
  });
});

