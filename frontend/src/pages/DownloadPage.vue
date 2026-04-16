<template>
  <div>
    <PageHeader
      title="Downloads"
      subtitle="Download existing outputs. This page does not trigger rebuilds or background work."
    />

    <ErrorAlert v-if="res.error" :error="res.error" />
    <LoadingBlock v-if="res.loading" title="Loading manifest..." description="Fetching available files." />

    <template v-else>
      <div class="row" style="align-items: center; justify-content: space-between; margin-bottom: 12px">
        <div class="pill">
          <span>Task</span>
          <code class="mono">{{ taskId }}</code>
        </div>
        <RouterLink class="btn" :to="{ name: 'task', params: { taskId } }">Back to status</RouterLink>
      </div>

      <div v-if="manifest && isSuccessManifest" class="row" style="margin-bottom: 12px">
        <div class="col card">
          <div class="card-inner">
            <div class="label">Language</div>
            <select class="select" v-model="selectedLang" @change="persistLang">
              <option v-for="f in files" :key="f.lang" :value="f.lang">{{ f.display_name }}</option>
            </select>
            <div class="help">
              Subtitle downloads require an explicit <code class="mono">lang</code> + <code class="mono">format</code>.
              The selector above controls which language is used.
            </div>
          </div>
        </div>
      </div>

      <EmptyState
        v-if="!manifest"
        title="No manifest"
        description="The results manifest is not available yet. Check task status first."
      >
        <RouterLink class="btn primary" :to="{ name: 'task', params: { taskId } }">Go to status</RouterLink>
      </EmptyState>

      <EmptyState
        v-else-if="!isSuccessManifest"
        title="Results not ready"
        description="The task has not completed yet, so downloads are not available. Go back to the status page and wait for SUCCESS."
      >
        <RouterLink class="btn primary" :to="{ name: 'task', params: { taskId } }">Go to status</RouterLink>
      </EmptyState>

      <DownloadList v-else :items="downloadItems" />

      <div v-if="manifest && !manifest.has_video" class="card" style="margin-top: 12px">
        <div class="card-inner">
          <div class="label">Note</div>
          <div class="help">
            <div>
              <strong>final.mp4 is missing.</strong> This can happen if the task did not generate a final video, or if a subtitle was edited
              and the backend deleted final.mp4 to avoid serving an outdated video.
            </div>
            <div style="margin-top: 6px">
              Editing subtitles only updates the subtitle file; it does not rebuild/burn the final video automatically.
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import PageHeader from "@/components/PageHeader.vue";
import DownloadList from "@/components/DownloadList.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import EmptyState from "@/components/EmptyState.vue";
import { useResultStore } from "@/stores/result";
import type { DownloadItem } from "@/types/result";
import { buildDownloadUrl } from "@/api/results";
import { usePreferencesStore } from "@/stores/preferences";

const props = defineProps<{ taskId: string }>();
const taskId = computed(() => props.taskId);

const res = useResultStore();
const prefs = usePreferencesStore();
const selectedLang = ref(prefs.preferredLang);

const manifest = computed(() => res.manifest);
const files = computed(() => manifest.value?.available_files ?? []);
const isSuccessManifest = computed(() => {
  const s = manifest.value?.task_status;
  if (!s) return true; // backwards-compat for older manifests
  return String(s).toUpperCase() === "SUCCESS";
});

watch(
  files,
  (list) => {
    if (list.length === 0) return;
    const exists = list.some((f) => f.lang === selectedLang.value);
    if (!exists) {
      selectedLang.value = list[0].lang;
      persistLang();
    }
  },
  { immediate: true }
);

function persistLang() {
  prefs.setPreferredLang(selectedLang.value);
}

const downloadItems = computed<DownloadItem[]>(() => {
  if (!manifest.value) return [];
  const items: DownloadItem[] = [];

  items.push({
    key: "video",
    label: "Final Video (final.mp4)",
    description: "Download the final video if it exists.",
    available: manifest.value.has_video,
    url: manifest.value.has_video ? buildDownloadUrl(taskId.value) : undefined,
  });

  const langInfo = files.value.find((f) => f.lang === selectedLang.value);
  const hasAss = Boolean(langInfo?.ass);
  const hasSrt = Boolean(langInfo?.srt);

  items.push({
    key: "ass",
    label: `Subtitle (ASS) - ${selectedLang.value}`,
    available: hasAss,
    url: hasAss ? buildDownloadUrl(taskId.value, "ass", selectedLang.value) : undefined,
  });

  items.push({
    key: "srt",
    label: `Subtitle (SRT) - ${selectedLang.value}`,
    available: hasSrt,
    url: hasSrt ? buildDownloadUrl(taskId.value, "srt", selectedLang.value) : undefined,
  });

  items.push({
    key: "vtt",
    label: `Subtitle (VTT) - ${selectedLang.value}`,
    description: "Generated on-the-fly from SRT.",
    available: hasSrt,
    url: hasSrt ? buildDownloadUrl(taskId.value, "vtt", selectedLang.value) : undefined,
  });

  return items;
});

watch(
  taskId,
  async (next) => {
    if (!next) return;
    // Reset UI selection to the current preference; manifest watcher will correct if unavailable.
    selectedLang.value = prefs.preferredLang;
    await res.fetchManifest(next);
  },
  { immediate: true }
);
</script>
