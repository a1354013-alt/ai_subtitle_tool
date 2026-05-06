<template>
  <div class="card">
    <div class="card-inner">
      <div v-if="!batchId">
        <form @submit.prevent="onSubmit">
          <div class="row">
            <div class="col">
              <div class="label">Select Videos</div>
              <input class="input" type="file" accept=".mp4,.mkv,.avi,.mov" multiple @change="onFilesChange" />
              <div class="help">
                Supported: {{ config.supportedExtensions.join(", ") }}. Max {{ config.maxUploadSizeMb }}MB per file,
                up to {{ config.maxBatchFiles }} files per batch.
              </div>
              <div v-if="validationError" class="task-error text-danger">{{ validationError }}</div>
              <div v-else-if="totalSizeText" class="help">Total selected size: {{ totalSizeText }}</div>
              <div v-if="files.length > 0" class="file-list">
                <div v-for="(f, i) in files" :key="i" class="file-item">
                  {{ f.name }} ({{ (f.size / 1024 / 1024).toFixed(1) }} MB)
                </div>
              </div>
            </div>

            <div class="col">
              <div class="label">Target Languages</div>
              <input v-model="targetLangs" class="input" type="text" placeholder="Traditional Chinese" />
              <div class="help">Comma-separated languages.</div>
            </div>
          </div>

          <div class="row" style="margin-top: 12px">
            <div class="col">
              <div class="label">Subtitle Format</div>
              <select v-model="subtitleFormat" class="select">
                <option value="ass">ass</option>
                <option value="srt">srt</option>
              </select>
            </div>

            <div class="col">
              <div class="label">Burn Subtitles</div>
              <label class="check">
                <input v-model="burnSubtitles" type="checkbox" />
                <span>Burn subtitles into final.mp4</span>
              </label>
            </div>
          </div>

          <div class="divider" />

          <div class="row" style="align-items: center; justify-content: flex-end">
            <button class="btn primary" type="submit" :disabled="submitting || files.length === 0 || !!validationError">
              {{ submitting ? 'Uploading...' : 'Start Batch Process' }}
            </button>
          </div>
        </form>
      </div>

      <div v-else>
        <div class="batch-header">
          <h3>Batch ID: {{ batchId }}</h3>
          <div class="batch-summary">
            <span>Total: {{ batchStatus?.total || 0 }}</span> |
            <span class="text-success">Completed: {{ batchStatus?.completed || 0 }}</span> |
            <span class="text-danger">Failed: {{ batchStatus?.failed || 0 }}</span> |
            <span>Processing: {{ batchStatus?.processing || 0 }}</span> |
            <span>Pending: {{ batchStatus?.pending || 0 }}</span>
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
              <a
                v-for="link in taskDownloadLinks(task)"
                :key="link.key"
                :href="link.href"
                class="btn-link"
                target="_blank"
              >
                {{ link.label }}
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { getBatchStatus, uploadBatch, downloadBatch } from "@/api/batch";
import { getAppConfig } from "@/api/config";
import { buildApiUrl } from "@/api/client";
import type { AppConfig, BatchStatusResponse, BatchTaskResponse } from "@/types/api";
import type { APIError } from "@/types/api";

const files = ref<File[]>([]);
const submitting = ref(false);
const batchId = ref<string | null>(null);
const batchStatus = ref<BatchStatusResponse | null>(null);
const targetLangs = ref("Traditional Chinese");
const subtitleFormat = ref("ass");
const burnSubtitles = ref(true);
const validationError = ref("");
const config = ref<AppConfig>({
  maxUploadSizeMb: 2048,
  maxBatchFiles: 20,
  supportedExtensions: [".mp4", ".mkv", ".avi", ".mov"],
  batchUploadEnabled: true,
  subtitleFormats: ["srt", "ass", "vtt"],
});
const showDownloadZip = computed(() => (batchStatus.value?.completed ?? 0) > 0);
const totalSizeText = computed(() =>
  files.value.length > 0 ? `${(files.value.reduce((sum, file) => sum + file.size, 0) / 1024 / 1024).toFixed(1)} MB` : ""
);

let statusInterval: any = null;

function formatSupportedExtensions() {
  return config.value.supportedExtensions.join(", ");
}

function validateSelectedFiles(selectedFiles: File[]): string {
  if (selectedFiles.length === 0) return "Select at least one file.";
  if (selectedFiles.length > config.value.maxBatchFiles) {
    return `You can upload up to ${config.value.maxBatchFiles} files at a time.`;
  }

  const maxBytes = config.value.maxUploadSizeMb * 1024 * 1024;
  for (const file of selectedFiles) {
    const extension = file.name.includes(".") ? `.${file.name.split(".").pop()!.toLowerCase()}` : "";
    if (!extension || !config.value.supportedExtensions.includes(extension)) {
      return `Unsupported file format: ${file.name}. Supported formats: ${formatSupportedExtensions()}.`;
    }
    if (file.size <= 0) {
      return `Empty files cannot be uploaded: ${file.name}.`;
    }
    if (file.size > maxBytes) {
      return `${file.name} exceeds the ${config.value.maxUploadSizeMb}MB per-file limit.`;
    }
  }

  return "";
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
  submitting.value = true;
  
  const fd = new FormData();
  files.value.forEach((file) => fd.append("files", file));
  fd.append("target_langs", targetLangs.value);
  fd.append("subtitle_format", subtitleFormat.value);
  fd.append("burn_subtitles", String(burnSubtitles.value));
  fd.append("parallel", "true");

  try {
    const response = await uploadBatch(fd);
    batchId.value = response.batch_id;
    startPolling();
  } catch (err) {
    const apiError = err as APIError;
    validationError.value = apiError.suggestion
      ? `${apiError.message} ${apiError.suggestion}`
      : apiError.message || "Batch upload failed";
  } finally {
    submitting.value = false;
  }
}

function startPolling() {
  fetchStatus();
  statusInterval = setInterval(fetchStatus, 3000);
}

async function fetchStatus() {
  if (!batchId.value) return;
  try {
    const response = await getBatchStatus(batchId.value);
    batchStatus.value = response;
    if (response.processing === 0 && response.pending === 0 && response.total > 0) {
      clearInterval(statusInterval);
    }
  } catch (err) {
    console.error("Failed to fetch batch status", err);
  }
}

function downloadZip() {
  if (!batchId.value) return;
  window.open(downloadBatch(batchId.value), "_blank");
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
  const links: Array<{ key: string; label: string; href: string }> = [];
  const downloadUrls = task.download_urls;
  if (!downloadUrls) return links;

  if (downloadUrls.video) {
    links.push({
      key: `${task.task_id}-video`,
      label: "Video",
      href: buildApiUrl(downloadUrls.video),
    });
  }

  for (const [language, formats] of Object.entries(downloadUrls.subtitles ?? {})) {
    if (formats.srt) {
      links.push({ key: `${task.task_id}-${language}-srt`, label: `${language} SRT`, href: buildApiUrl(formats.srt) });
    }
    if (formats.ass) {
      links.push({ key: `${task.task_id}-${language}-ass`, label: `${language} ASS`, href: buildApiUrl(formats.ass) });
    }
    if (formats.vtt) {
      links.push({ key: `${task.task_id}-${language}-vtt`, label: `${language} VTT`, href: buildApiUrl(formats.vtt) });
    }
  }

  return links;
}

onUnmounted(() => {
  if (statusInterval) clearInterval(statusInterval);
});

onMounted(async () => {
  try {
    config.value = await getAppConfig();
  } catch {
    // Keep the built-in defaults when config cannot be fetched.
  }
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
  color: var(--color-primary);
  text-decoration: none;
  font-size: 0.9em;
}
.text-success { color: #4caf50; }
.text-danger { color: #f44336; }
.text-muted { color: #888; }
</style>
