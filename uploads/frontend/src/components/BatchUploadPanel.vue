<template>
  <div class="card">
    <div class="card-inner">
      <div v-if="!batchId">
        <form @submit.prevent="onSubmit">
          <div class="row">
            <div class="col">
              <div class="label">Select Videos</div>
              <input class="input" type="file" accept=".mp4,.mkv,.avi,.mov" multiple @change="onFilesChange" />
              <div class="help">You can select multiple videos. Max 2GB per file.</div>
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
            <button class="btn primary" type="submit" :disabled="submitting || files.length === 0">
              {{ submitting ? "Uploading..." : "Start Batch Process" }}
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
            <span>Processing: {{ batchStatus?.processing || 0 }}</span>
          </div>
          <button v-if="(batchStatus?.completed ?? 0) > 0" class="btn primary btn-sm" @click="downloadZip">
            {{ $t("batch.downloadZip") }}
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
            <div v-if="isSuccessStatus(task.status) && task.download_urls" class="task-actions">
              <a :href="toAbsoluteUrl(task.download_urls.srt)" class="btn-link" target="_blank" rel="noopener">SRT</a>
              <a :href="toAbsoluteUrl(task.download_urls.ass)" class="btn-link" target="_blank" rel="noopener">ASS</a>
              <a :href="toAbsoluteUrl(task.download_urls.video)" class="btn-link" target="_blank" rel="noopener">Video</a>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from "vue";
import axios from "axios";
import { buildApiUrl } from "@/api/client";

type BatchDownloadUrls = {
  srt: string;
  ass: string;
  video: string;
};

type BatchTask = {
  task_id: string;
  filename: string;
  status: string;
  progress: number;
  message?: string | null;
  error?: string | null;
  download_urls?: BatchDownloadUrls | null;
};

type BatchStatusResponse = {
  batch_id: string;
  total: number;
  completed: number;
  failed: number;
  processing: number;
  tasks: BatchTask[];
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";
const files = ref<File[]>([]);
const submitting = ref(false);
const batchId = ref<string | null>(null);
const batchStatus = ref<BatchStatusResponse | null>(null);
const targetLangs = ref("Traditional Chinese");
const subtitleFormat = ref("ass");
const burnSubtitles = ref(true);

let statusInterval: ReturnType<typeof setInterval> | null = null;

function normalizeStatus(status: string | null | undefined): string {
  return String(status ?? "").toUpperCase();
}

function isSuccessStatus(status: string | null | undefined): boolean {
  return normalizeStatus(status) === "SUCCESS";
}

function isFailedStatus(status: string | null | undefined): boolean {
  return ["FAILURE", "FAILED", "ERROR"].includes(normalizeStatus(status));
}

function isProcessingStatus(status: string | null | undefined): boolean {
  return ["PROCESSING", "PENDING", "STARTED", "QUEUED"].includes(normalizeStatus(status));
}

function statusLabel(status: string | null | undefined): string {
  if (isSuccessStatus(status)) return "Completed";
  if (isFailedStatus(status)) return "Failed";
  if (isProcessingStatus(status)) return "Processing";
  return "Unknown";
}

function statusClass(status: string | null | undefined): string {
  if (isSuccessStatus(status)) return "text-success";
  if (isFailedStatus(status)) return "text-danger";
  if (isProcessingStatus(status)) return "text-muted";
  return "text-muted";
}

function toAbsoluteUrl(path: string | undefined): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  if (apiBaseUrl) return `${apiBaseUrl}${path}`;
  return buildApiUrl(path);
}

function onFilesChange(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files) {
    files.value = Array.from(input.files);
  }
}

async function onSubmit() {
  if (files.value.length === 0) return;
  submitting.value = true;

  const fd = new FormData();
  files.value.forEach((f) => fd.append("files", f));
  fd.append("target_langs", targetLangs.value);
  fd.append("subtitle_format", subtitleFormat.value);
  fd.append("burn_subtitles", String(burnSubtitles.value));
  fd.append("parallel", "true");

  try {
    const res = await axios.post(`${apiBaseUrl}/batch/upload`, fd);
    batchId.value = res.data.batch_id;
    startPolling();
  } catch (err) {
    console.error("Batch upload failed", err);
    alert("Batch upload failed");
  } finally {
    submitting.value = false;
  }
}

function startPolling() {
  void fetchStatus();
  statusInterval = setInterval(() => {
    void fetchStatus();
  }, 3000);
}

async function fetchStatus() {
  if (!batchId.value) return;
  try {
    const res = await axios.get(`${apiBaseUrl}/batch/${batchId.value}/status`);
    batchStatus.value = res.data;
    if (res.data.processing === 0 && res.data.total > 0 && statusInterval) {
      clearInterval(statusInterval);
      statusInterval = null;
    }
  } catch (err) {
    console.error("Failed to fetch batch status", err);
  }
}

function downloadZip() {
  if (!batchId.value) return;
  window.open(`${apiBaseUrl}/batch/${batchId.value}/download`, "_blank");
}

onUnmounted(() => {
  if (statusInterval) clearInterval(statusInterval);
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
.text-success {
  color: #4caf50;
}
.text-danger {
  color: #f44336;
}
.text-muted {
  color: #888;
}
</style>
