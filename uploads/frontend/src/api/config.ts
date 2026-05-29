import { apiRequest } from "./client";

export interface AppConfig {
  translate_provider: string;
  ollama_model: string;
  translate_model: string;
}

export async function getAppConfig(): Promise<AppConfig> {
  return apiRequest<AppConfig>("/api/config");
}
