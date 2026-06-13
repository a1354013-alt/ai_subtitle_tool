<template>
  <div class="card">
    <div class="card-inner">
      <form @submit.prevent="onSubmit">
        <div class="row">
          <div class="col">
            <div class="label">{{ $t('upload.selectVideo') }}</div>
            <input class="input" type="file" accept=".mp4,.mkv,.avi,.mov" @change="onFileChange" />
            <div class="help">
              {{ $t('upload.supportedHelp', { extensions: config.supportedExtensions.join(', '), maxMb: config.maxUploadSizeMb }) }}
            </div>
            <div v-if="validationError" class="task-error text-danger">{{ validationError }}</div>
          </div>

          <div class="col">
            <div class="label">{{ $t('upload.targetLanguages') }}</div>
            <input 
              v-model="targetLangs" 
              class="input" 
              type="text" 
              :placeholder="translationPlaceholder"
            />
            <div class="help" :class="isTranslationAvailable ? 'text-success' : 'text-warning'">
              {{ translationStatusMessage }}
            </div>
            <div v-if="isTranslationAvailable" class="help">
              {{ $t('upload.commaSeparatedHelp', { example: 'Traditional Chinese, English' }) }}
            </div>
          </div>
        </div>

        <div class="row" style="margin-top: 12px">
          <div class="col">
            <div class="label">{{ $t('upload.subtitleFormat') }}</div>
            <select v-model="subtitleFormat" class="select">
              <option value="ass">ass</option>
              <option value="srt">srt</option>
            </select>
          </div>

          <div class="col">
            <div class="label">{{ $t('upload.burnSubtitles') }}</div>
            <label class="check">
              <input v-model="burnSubtitles" type="checkbox" />
              <span>{{ $t('upload.burnIntoFinal') }}</span>
            </label>
          </div>

          <div class="col">
            <div class="label">{{ $t('upload.removeSilence') }}</div>
            <label class="check">
              <input v-model="removeSilence" type="checkbox" />
              <span>{{ $t('upload.removeSilenceHelp') }}</span>
            </label>
          </div>

          <div class="col">
            <div class="label">{{ $t('upload.parallel') }}</div>
            <label class="check">
              <input v-model="parallel" type="checkbox" />
              <span>{{ $t('upload.parallelHelp') }}</span>
            </label>
          </div>
        </div>

        <div class="divider" />

        <div class="row" style="align-items: center; justify-content: space-between">
          <div class="pill">
            <span>{{ $t('upload.apiBaseUrl') }}</span>
            <code class="mono">{{ apiBaseUrl }}</code>
          </div>
          <button class="btn primary" type="submit" :disabled="props.submitting || !file">
            {{ props.submitting ? $t('upload.uploading') : $t('upload.generate') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useI18n } from "vue-i18n";
import { getAppCapabilities } from "@/api/capabilities";
import { getAppConfig } from "@/api/config";
import type { AppCapabilities, AppConfig } from "@/types/api";
import type { SubtitleFormat } from "@/types/subtitle";
import { getTranslationStatusMessage, translationTargetsRequested } from "@/utils/translation";

const emit = defineEmits<{
  (e: "submit", payload: FormData): void;
}>();
const { t } = useI18n();

const file = ref<File | null>(null);
const props = withDefaults(
  defineProps<{
    submitting?: boolean;
  }>(),
  { submitting: false }
);

const targetLangs = ref("Original");
const subtitleFormat = ref<SubtitleFormat>("ass");
const burnSubtitles = ref(true);
const removeSilence = ref(false);
const parallel = ref(true);
const validationError = ref("");
const config = ref<AppConfig>({
  maxUploadSizeMb: 2048,
  maxBatchFiles: 20,
  supportedExtensions: [".mp4", ".mkv", ".avi", ".mov"],
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
const capabilities = ref<AppCapabilities>({
  provider: "none",
  model: null,
  translationEnabled: false,
  reason: "translation_disabled",
  message: null,
  defaultTargetLanguage: "Original",
  availableModes: ["transcribe"],
  openaiConfigured: false,
});

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "(same origin)";

const isTranslationAvailable = computed(() => {
  return capabilities.value.translationEnabled;
});

const translationPlaceholder = computed(() => {
  if (isTranslationAvailable.value) {
    return "Traditional Chinese";
  }
  return t("upload.translationOnlyPlaceholder");
});

const translationStatusMessage = computed(() => getTranslationStatusMessage(capabilities.value, t));

function validateSelectedFile(selected: File | null): string {
  if (!selected) return "";
  const extension = selected.name.includes(".") ? `.${selected.name.split(".").pop()!.toLowerCase()}` : "";
  if (!extension || !config.value.supportedExtensions.includes(extension)) {
    return t("upload.unsupportedFile", { filename: selected.name, formats: config.value.supportedExtensions.join(", ") });
  }
  if (selected.size <= 0) {
    return t("upload.emptyFile", { filename: selected.name });
  }
  const maxBytes = config.value.maxUploadSizeMb * 1024 * 1024;
  if (selected.size > maxBytes) {
    return t("upload.fileTooLarge", { filename: selected.name, maxMb: config.value.maxUploadSizeMb });
  }
  return "";
}

function applyDefaultTargetLanguage() {
  targetLangs.value = capabilities.value.defaultTargetLanguage || "Original";
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const selected = input.files?.[0] ?? null;
  validationError.value = validateSelectedFile(selected);
  if (validationError.value) {
    input.value = "";
    file.value = null;
    return;
  }
  file.value = selected;
}

async function onSubmit() {
  validationError.value = validateSelectedFile(file.value);
  if (!file.value || validationError.value) return;
  if (translationTargetsRequested(targetLangs.value) && !isTranslationAvailable.value) {
    validationError.value = translationStatusMessage.value;
    return;
  }
  const fd = new FormData();
  fd.append("file", file.value);
  fd.append("target_langs", translationTargetsRequested(targetLangs.value) ? targetLangs.value : "Original");
  fd.append("subtitle_format", subtitleFormat.value);
  fd.append("burn_subtitles", String(burnSubtitles.value));
  fd.append("remove_silence", String(removeSilence.value));
  fd.append("parallel", String(parallel.value));
  emit("submit", fd);
}

onMounted(async () => {
  const [configResult, capabilitiesResult] = await Promise.allSettled([getAppConfig(), getAppCapabilities()]);
  if (configResult.status === "fulfilled") {
    config.value = configResult.value;
  }
  if (capabilitiesResult.status === "fulfilled") {
    capabilities.value = capabilitiesResult.value;
  }
  applyDefaultTargetLanguage();
});
</script>

<style scoped>
.check {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  color: var(--color-muted);
}
</style>
