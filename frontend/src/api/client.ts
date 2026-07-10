import type { APIError } from "@/types/api";

const DEFAULT_TIMEOUT_MS = 30_000;
export const UPLOAD_TIMEOUT_MS = 0;

type RequestOptions = RequestInit & {
  timeoutMs?: number | null;
  timeoutMessage?: string;
};

export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL;
  if (!raw && import.meta.env.DEV && import.meta.env.MODE !== "test") {
    console.warn(
      "VITE_API_BASE_URL not set; using same-origin. This may fail in cross-origin setups."
    );
  }
  const baseUrl = (raw ?? "").replace(/\/$/, "");
  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
}

export function buildApiUrl(path: string): string {
  const baseUrl = getApiBaseUrl();
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${baseUrl}${normalized}`;
}

export function buildRequestHeaders(headers?: HeadersInit): HeadersInit | undefined {
  const apiToken = (import.meta.env.VITE_API_TOKEN ?? "").trim();
  if (!apiToken) return headers;

  const merged = new Headers(headers);
  if (!merged.has("X-API-Token")) {
    merged.set("X-API-Token", apiToken);
  }
  return merged;
}

export async function apiRequest<T>(
  path: string,
  init: RequestOptions = {}
): Promise<T> {
  const url = buildApiUrl(path);

  const controller = new AbortController();
  const timeoutMs = init.timeoutMs === undefined ? DEFAULT_TIMEOUT_MS : init.timeoutMs;
  const timeout =
    timeoutMs && timeoutMs > 0
      ? window.setTimeout(
          () => controller.abort(),
          timeoutMs
        )
      : null;

  try {
    const fetchInit = { ...init };
    delete fetchInit.timeoutMs;
    delete fetchInit.timeoutMessage;
    const res = await fetch(url, {
      ...fetchInit,
      headers: buildRequestHeaders(init.headers),
      signal: controller.signal,
    });

    const contentType = res.headers.get("content-type") ?? "";
    const isJson = contentType.includes("application/json");

    if (!res.ok) {
      let detail: unknown = undefined;
      let message = `Request failed (${res.status})`;
      let error_code: string | undefined = undefined;
      let suggestion: string | undefined = undefined;

      try {
        if (isJson) {
          const body = (await res.json()) as any;
          detail = body;
          
          if (body?.error_code) {
            error_code = body.error_code;
            message = body?.message ?? message;
            suggestion = body?.suggestion;
          } else if (body?.detail) {
            message = body.detail;
          } else if (body?.message) {
            message = body.message;
          }
        } else {
          const text = await res.text();
          detail = text;
          if (text) message = text;
        }
      } catch {
        // ignore parsing errors
      }

      const err: APIError = { message, status: res.status, detail, error_code, suggestion };
      throw err;
    }

    if (res.status === 204) return undefined as T;
    if (isJson) return (await res.json()) as T;

    // 這個前端 API 目前只需要 JSON；若後續擴充可在這裡加入其他 parsing
    return (await res.text()) as unknown as T;
  } catch (e: any) {
    if (e?.name === "AbortError") {
      const err: APIError = { message: init.timeoutMessage ?? "Request timeout", status: 408 };
      throw err;
    }
    throw e;
  } finally {
    if (timeout !== null) {
      window.clearTimeout(timeout);
    }
  }
}

export function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}
