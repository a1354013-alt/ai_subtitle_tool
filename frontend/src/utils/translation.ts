import type { AppCapabilities } from "@/types/api";

type TranslateFn = (key: string, args?: Record<string, unknown>) => string;

export function translationTargetsRequested(rawTargetLangs: string): boolean {
  return rawTargetLangs
    .split(",")
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean)
    .some((lang) => !["original", "source", "auto"].includes(lang));
}

export function getTranslationStatusMessage(
  capabilities: AppCapabilities,
  t: TranslateFn
): string {
  if (capabilities.provider === "ollama") {
    if (capabilities.translationEnabled) {
      return t("upload.translationEnabledOllama", { model: capabilities.model ?? "unknown" });
    }
    return t("upload.translationUnavailableOllama");
  }

  if (capabilities.provider === "openai") {
    if (capabilities.translationEnabled) {
      return t("upload.translationEnabledOpenAI", { model: capabilities.model ?? "unknown" });
    }
    return t("upload.translationUnavailableOpenAI");
  }

  return t("upload.translationDisabled");
}
