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
import { computed, ref, onUnmounted } from "vue";
import axios from "axios";
import { buildApiUrl } from "@/api/client";
import type { BatchStatusResponse, BatchTaskResponse } from "@/types/api";

const files = ref<File[]>([]);
const submitting = ref(false);
const batchId = ref<string | null>(null);
const batchStatus = ref<BatchStatusResponse | null>(null);
const targetLangs = ref("Traditional Chinese");
const subtitleFormat = ref("ass");
const burnSubtitles = ref(true);
const showDownloadZip = computed(() => (batchStatus.value?.completed ?? 0) > 0);

let statusInterval: any = null;

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
  files.value.forEach(f => fd.append("files", f));
  fd.append("target_langs", targetLangs.value);
  fd.append("subtitle_format", subtitleFormat.value);
  fd.append("burn_subtitles", String(burnSubtitles.value));
  fd.append("parallel", "true");

  try {
    const res = await axios.post(buildApiUrl("/batch/upload"), fd);
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
  fetchStatus();
  statusInterval = setInterval(fetchStatus, 3000);
}

async function fetchStatus() {
  if (!batchId.value) return;
  try {
    const res = await axios.get(buildApiUrl(`/batch/${batchId.value}/status`));
    batchStatus.value = res.data;
    if (res.data.processing === 0 && res.data.pending === 0 && res.data.total > 0) {
      clearInterval(statusInterval);
    }
  } catch (err) {
    console.error("Failed to fetch batch status", err);
  }
}

function downloadZip() {
  if (!batchId.value) return;
  window.open(buildApiUrl(`/batch/${batchId.value}/download`), "_blank");
}

function normalizeStatus(status: string) {
  return String(status || "").toUpperCase();
}

function isSuccessStatus(status: string) {
  return normalizeStatus(status) === "SUCCESS";
}

function statusClass(status: string) {
  if (isSuccessStatus(status)) return "text-success";
  if (normalizeStatus(status) === "FAILURE") return "text-danger";
  return "text-muted";
}

function statusLabel(status: string) {
  const normalized = normalizeStatus(status);
  if (normalized === "SUCCESS") return "SUCCESS";
  if (normalized === "FAILURE") return "FAILURE";
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
