<template>
  <div class="card">
    <div class="card-inner">
      <div v-if="!batchId">
        <form @submit.prevent="onSubmit">
          <div class="row">
            <div class="col">
              <div class="label">{{ $t('batch.selectVideos') }}</div>
              <input class="input" type="file" accept=".mp4,.mkv,.avi,.mov" multiple @change="onFilesChange" />
              <div class="help">
                {{ $t('batch.supportedHelp', { extensions: config.supportedExtensions.join(', '), maxMb: config.maxUploadSizeMb, maxFiles: config.maxBatchFiles }) }}
              </div>
              <div v-if="validationError" class="task-error text-danger">{{ validationError }}</div>
              <div v-else-if="totalSizeText" class="help">{{ $t('batch.totalSelectedSize', { size: totalSizeText }) }}</div>
              <div v-if="files.length > 0" class="file-list">
                <div v-for="(f, i) in files" :key="i" class="file-item">
                  {{ f.name }} ({{ (f.size / 1024 / 1024).toFixed(1) }} MB)
                </div>
              </div>
            </div>

            <div class="col">
              <div class="label">{{ $t('upload.targetLanguages') }}</div>
              <input 
                v-model="targetLangs" 
                class="input" 
                type="text" 
                placeholder="Original"
              />
              <div class="help" :class="isTranslationAvailable ? 'text-success' : 'text-warning'">
                {{ translationStatusMessage }}
              </div>
              <div v-if="isTranslationAvailable" class="help">
                {{ $t('batch.commaSeparatedLanguages') }}
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
                <span>{{ $t('batch.burnIntoFinal') }}</span>
              </label>
            </div>
          </div>

          <div class="row" style="margin-top: 12px">
            <div class="col">
              <div class="label">{{ $t('upload.removeSilence') }}</div>
              <label class="check">
                <input v-model="removeSilence" type="checkbox" />
                <span>{{ $t('batch.removeSilenceHelp') }}</span>
              </label>
            </div>
          </div>

          <div class="divider" />

          <div class="row" style="align-items: center; justify-content: flex-end">
            <button class="btn primary" type="submit" :disabled="submitting || files.length === 0 || !!validationError">
              {{ submitting ? $t('batch.uploading') : $t('batch.startProcess') }}
            </button>
          </div>
        </form>
      </div>

      <div v-else>
        <div class="batch-header">
          <h3>{{ $t('batch.batchId') }}: {{ batchId }}</h3>
          <div v-if="pollingError" class="task-error text-danger">{{ pollingError }}</div>
          <div class="batch-summary">
            <span>{{ $t('batch.total') }}: {{ batchStatus?.total || 0 }}</span> |
            <span class="text-success">{{ $t('task.completed') }}: {{ batchStatus?.completed || 0 }}</span> |
            <span class="text-danger">{{ $t('task.failed') }}: {{ batchStatus?.failed || 0 }}</span> |
            <span>{{ $t('task.processing') }}: {{ batchStatus?.processing || 0 }}</span> |
            <span>{{ $t('batch.pending') }}: {{ batchStatus?.pending || 0 }}</span>
          </div>
          <button v-if="showDownloadZip" class="btn primary btn-sm" @click="downloadZip">
            {{ $t('batch.downloadZip') }}
          </button>
        </div>

        <div class="task-list">
          <div v-for="task in batchStatus?.tasks" :key="task.task_id" class="task-item">
            <div class="task-info">
              <div class="task-filename">{{ task.filename }}</div>
              <div class="task-status">
                <span :class="statusClass(task.status)">{{ statusLabel(task.status) }}</span>
                <span v-if="task.progress > 0"> - {{ task.progress }}%</span>
              </div>
            </div>
            <div v-if="task.error" class="task-error text-danger">{{ task.error }}</div>
            <div v-if="hasDownloads(task)" class="task-actions">
              <button
                v-for="link in taskDownloadLinks(task)"
                :key="link.key"
                class="btn-link"
                type="button"
                @click="openDownloadPath(link.path)"
              >
                {{ link.label }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { createBatchDownloadTicket, getBatchStatus, uploadBatch } from "@/api/batch";
import { getAppConfig } from "@/api/config";
import { createDownloadTicket } from "@/api/results";
import type { AppCapabilities, AppConfig, BatchStatusResponse, BatchTaskResponse } from "@/types/api";
import type { APIError } from "@/types/api";
import { getTranslationStatusMessage, translationTargetsRequested } from "@/utils/translation";

const files = ref<File[]>([]);
const { t } = useI18n();
const submitting = ref(false);
const batchId = ref<string | null>(null);
const batchStatus = ref<BatchStatusResponse | null>(null);
const targetLangs = ref("Original");
const subtitleFormat = ref("ass");
const burnSubtitles = ref(true);
const removeSilence = ref(false);
const validationError = ref("");
const pollingError = ref("");
const config = ref<AppConfig>({
  version: "0.0.0",
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
const showDownloadZip = computed(() => (batchStatus.value?.completed ?? 0) > 0);
const totalSizeText = computed(() =>
  files.value.length > 0 ? `${(files.value.reduce((sum, file) => sum + file.size, 0) / 1024 / 1024).toFixed(1)} MB` : ""
);

let statusInterval: any = null;

const isTranslationAvailable = computed(() => capabilities.value.translationEnabled);
const translationStatusMessage = computed(() => getTranslationStatusMessage(capabilities.value, t));

function capabilitiesFromConfig(value: AppConfig): AppCapabilities {
  return {
    provider: value.provider,
    model: value.model,
    translationEnabled: value.translationEnabled,
    reason: value.reason,
    message: value.message,
    defaultTargetLanguage: value.defaultTargetLanguage,
    availableModes: value.availableModes,
    openaiConfigured: value.openaiConfigured,
  };
}

function formatSupportedExtensions() {
  return config.value.supportedExtensions.join(", ");
}

function validateSelectedFiles(selectedFiles: File[]): string {
  if (selectedFiles.length === 0) return t("batch.selectAtLeastOne");
  if (selectedFiles.length > config.value.maxBatchFiles) {
    return t("batch.tooManyFiles", { maxFiles: config.value.maxBatchFiles });
  }

  const maxBytes = config.value.maxUploadSizeMb * 1024 * 1024;
  for (const file of selectedFiles) {
    const extension = file.name.includes(".") ? `.${file.name.split(".").pop()!.toLowerCase()}` : "";
    if (!extension || !config.value.supportedExtensions.includes(extension)) {
      return t("batch.unsupportedFile", { filename: file.name, formats: formatSupportedExtensions() });
    }
    if (file.size <= 0) {
      return t("batch.emptyFile", { filename: file.name });
    }
    if (file.size > maxBytes) {
      return t("batch.fileTooLarge", { filename: file.name, maxMb: config.value.maxUploadSizeMb });
    }
  }

  return "";
}

function applyDefaultTargetLanguage() {
  targetLangs.value = capabilities.value.defaultTargetLanguage || "Original";
}

function onFilesChange(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files) {
    const selectedFiles = Array.from(input.files);
    validationError.value = validateSelectedFiles(selectedFiles);
    files.value = validationError.value ? [] : selectedFiles;
  }
}

async function onSubmit() {
  validationError.value = validateSelectedFiles(files.value);
  if (files.value.length === 0 || validationError.value) return;
  if (translationTargetsRequested(targetLangs.value) && !isTranslationAvailable.value) {
    validationError.value = translationStatusMessage.value;
    return;
  }
  submitting.value = true;
  
  const fd = new FormData();
  files.value.forEach((file) => fd.append("files", file));
  fd.append("target_langs", translationTargetsRequested(targetLangs.value) ? targetLangs.value : "Original");
  fd.append("subtitle_format", subtitleFormat.value);
  fd.append("burn_subtitles", String(burnSubtitles.value));
  fd.append("remove_silence", String(removeSilence.value));
  fd.append("parallel", "true");

  try {
    const response = await uploadBatch(fd);
    batchId.value = response.batch_id;
    startPolling();
  } catch (err) {
    const apiError = err as APIError;
    validationError.value = apiError.suggestion
      ? `${apiError.message} ${apiError.suggestion}`
      : apiError.message || t("batch.uploadFailed");
  } finally {
    submitting.value = false;
  }
}

function startPolling() {
  pollingError.value = "";
  if (statusInterval) {
    clearInterval(statusInterval);
    statusInterval = null;
  }
  fetchStatus();
  statusInterval = setInterval(fetchStatus, 3000);
}

async function fetchStatus() {
  if (!batchId.value) return;
  try {
    const response = await getBatchStatus(batchId.value);
    pollingError.value = "";
    batchStatus.value = response;
    if (response.processing === 0 && response.pending === 0 && response.total > 0) {
      clearInterval(statusInterval);
      statusInterval = null;
    }
  } catch (err) {
    const apiError = err as APIError;
    pollingError.value = apiError.message || t("batch.fetchStatusFailed");
    if (apiError.status === 404 && statusInterval) {
      clearInterval(statusInterval);
      statusInterval = null;
    }
  }
}

async function downloadZip() {
  if (!batchId.value) return;
  window.open(await createBatchDownloadTicket(batchId.value), "_blank", "noopener");
}

async function openDownloadPath(path: string) {
  window.open(await createDownloadTicket(path), "_blank", "noopener");
}

function normalizeStatus(status: string) {
  return String(status || "").toUpperCase();
}

function isSuccessStatus(status: string) {
  return normalizeStatus(status) === "SUCCESS";
}

function statusClass(status: string) {
  if (isSuccessStatus(status)) return "text-success";
  if (["FAILURE", "CANCELED"].includes(normalizeStatus(status))) return "text-danger";
  return "text-muted";
}

function statusLabel(status: string) {
  const normalized = normalizeStatus(status);
  if (normalized === "SUCCESS") return "SUCCESS";
  if (normalized === "FAILURE") return "FAILURE";
  if (normalized === "CANCELED") return "CANCELED";
  if (normalized === "PROCESSING") return "PROCESSING";
  return "PENDING";
}

function hasDownloads(task: BatchTaskResponse) {
  return isSuccessStatus(task.status) && taskDownloadLinks(task).length > 0;
}

function taskDownloadLinks(task: BatchTaskResponse) {
  const links: Array<{ key: string; label: string; path: string }> = [];
  const downloadUrls = task.download_urls;
  if (!downloadUrls) return links;

  if (downloadUrls.video) {
    links.push({
      key: `${task.task_id}-video`,
      label: t("batch.video"),
      path: downloadUrls.video,
    });
  }

  for (const [language, formats] of Object.entries(downloadUrls.subtitles ?? {})) {
    if (formats.srt) {
      links.push({ key: `${task.task_id}-${language}-srt`, label: `${language} SRT`, path: formats.srt });
    }
    if (formats.ass) {
      links.push({ key: `${task.task_id}-${language}-ass`, label: `${language} ASS`, path: formats.ass });
    }
    if (formats.vtt) {
      links.push({ key: `${task.task_id}-${language}-vtt`, label: `${language} VTT`, path: formats.vtt });
    }
  }

  return links;
}

onUnmounted(() => {
  if (statusInterval) {
    clearInterval(statusInterval);
    statusInterval = null;
  }
});

onMounted(async () => {
  try {
    const appConfig = await getAppConfig();
    config.value = appConfig;
    capabilities.value = capabilitiesFromConfig(appConfig);
  } catch {
    // Keep local defaults when the config endpoint is unavailable during smoke tests or offline demos.
  }
  applyDefaultTargetLanguage();
});
</script>

<style scoped>
.file-list {
  margin-top: 10px;
  max-height: 150px;
  overflow-y: auto;
  font-size: 0.9em;
  background: rgba(255, 255, 255, 0.05);
  padding: 8px;
  border-radius: 8px;
}
.file-item {
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}
.batch-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 20px;
}
.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.task-item {
  padding: 12px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.task-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.task-filename {
  font-weight: bold;
}
.task-actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}
.btn-link {
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-primary);
  text-decoration: none;
  font-size: 0.9em;
  cursor: pointer;
}
.text-success { color: #4caf50; }
.text-danger { color: #f44336; }
.text-muted { color: #888; }
.text-warning { color: #ff9800; }
</style>
