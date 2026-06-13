import { apiRequest } from "./client";
import type { AppCapabilities } from "@/types/api";

export async function getAppCapabilities(): Promise<AppCapabilities> {
  return apiRequest<AppCapabilities>("/api/capabilities");
}
