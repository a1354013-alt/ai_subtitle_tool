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

import { buildDownloadUrl } from "@/api/results";

describe("buildDownloadUrl", () => {
  it("uses the shared buildApiUrl() base URL logic", () => {
    expect(buildDownloadUrl("abc")).toBe("http://api.example/download/abc");
  });

  it("includes lang+format when downloading subtitles", () => {
    expect(buildDownloadUrl("abc", "ass", "Traditional_Chinese")).toBe(
      "http://api.example/download/abc?lang=Traditional_Chinese&format=ass"
    );
  });

  it("requires lang when downloading subtitles", () => {
    expect(() => buildDownloadUrl("abc", "srt")).toThrow(/lang is required/i);
  });

  it("rejects unsupported formats without creating a download side effect", () => {
    const createElementSpy = vi.spyOn(document, "createElement");
    const createObjectUrlSpy = vi.spyOn(URL, "createObjectURL");
    const revokeObjectUrlSpy = vi.spyOn(URL, "revokeObjectURL");

    expect(() => buildDownloadUrl("abc", "exe" as any, "Traditional_Chinese")).toThrow(/unsupported subtitle format/i);
    expect(createElementSpy).not.toHaveBeenCalled();
    expect(createObjectUrlSpy).not.toHaveBeenCalled();
    expect(revokeObjectUrlSpy).not.toHaveBeenCalled();
  });
});
