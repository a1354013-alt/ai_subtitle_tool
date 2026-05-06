import { apiRequest } from "./client";
import type { AppConfig } from "@/types/api";

export async function getAppConfig(): Promise<AppConfig> {
  return apiRequest<AppConfig>("/api/config");
}
