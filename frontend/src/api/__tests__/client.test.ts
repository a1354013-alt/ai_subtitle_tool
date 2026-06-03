import { beforeEach, describe, expect, it, vi } from "vitest";

describe("buildRequestHeaders", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  it("does not send an API token header when VITE_API_TOKEN is empty", async () => {
    vi.stubEnv("VITE_API_TOKEN", "");
    const { buildRequestHeaders } = await import("@/api/client");

    const headers = buildRequestHeaders({ "Content-Type": "application/json" });

    expect(new Headers(headers).has("X-API-Token")).toBe(false);
    expect(new Headers(headers).get("Content-Type")).toBe("application/json");
  });

  it("adds X-API-Token when VITE_API_TOKEN is set", async () => {
    vi.stubEnv("VITE_API_TOKEN", "secret");
    const { buildRequestHeaders } = await import("@/api/client");

    const headers = new Headers(buildRequestHeaders());

    expect(headers.get("X-API-Token")).toBe("secret");
  });

  it("preserves existing headers and does not overwrite an explicit token", async () => {
    vi.stubEnv("VITE_API_TOKEN", "env-secret");
    const { buildRequestHeaders } = await import("@/api/client");

    const headers = new Headers(
      buildRequestHeaders({
        "Content-Type": "application/json",
        "X-API-Token": "request-secret",
      })
    );

    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-API-Token")).toBe("request-secret");
  });
});
