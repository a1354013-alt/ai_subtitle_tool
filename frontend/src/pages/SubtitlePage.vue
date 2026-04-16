<template>
  <div>
    <PageHeader
      title="Subtitles"
      subtitle="Edit subtitle files (ASS/SRT). Editing only updates the subtitle file; it does not rebuild/burn the final video."
    />

    <ErrorAlert v-if="sub.error" :error="sub.error" />

    <EmptyState
      v-if="!loading && manifestNotReady"
      title="Subtitles not ready"
      description="The task has not completed yet, so subtitle files are not available. Go back to the task status page and wait for SUCCESS."
    >
      <RouterLink class="btn primary" :to="{ name: 'task', params: { taskId: taskIdValue } }">Go to status</RouterLink>
    </EmptyState>

    <EmptyState
      v-else-if="!loading && noSubtitles"
      title="No subtitles available"
      description="This task does not have any downloadable subtitle files in the results manifest."
    >
      <RouterLink class="btn primary" :to="{ name: 'downloads', params: { taskId: taskIdValue } }">Go to downloads</RouterLink>
    </EmptyState>

    <div
      v-else
      class="row"
      style="align-items: center; justify-content: space-between; margin-bottom: 12px"
    >
      <div class="pill">
        <span>Task</span>
        <code class="mono">{{ taskIdValue }}</code>
      </div>

      <div class="row" style="align-items: center">
        <div class="pill" style="margin-right: 8px">
          <span>Editing</span>
          <code class="mono">{{ sub.lang }} / {{ sub.format.toUpperCase() }}</code>
        </div>

        <div class="pill">
          <span>Language</span>
          <select class="select" style="width: 220px" v-model="langSelection" @change="onLanguageChange">
            <option v-for="f in langOptions" :key="f.lang" :value="f.lang">{{ f.display_name }}</option>
          </select>
        </div>

        <SubtitleFormatTabs :model-value="formatSelection" @update:modelValue="onFormatChange" />

        <RouterLink class="btn" :to="{ name: 'downloads', params: { taskId: taskIdValue } }">Downloads</RouterLink>
      </div>
    </div>

    <LoadingBlock v-if="loading" title="Loading subtitle..." description="Fetching subtitle content." />

    <SubtitleEditor
      v-else-if="!manifestNotReady && !noSubtitles"
      v-model="editorModel"
      :dirty="sub.isDirty"
      :saving="sub.saving"
      :last-saved-at="sub.lastSavedAt"
      @save="save"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, onBeforeRouteLeave, onBeforeRouteUpdate } from "vue-router";
import PageHeader from "@/components/PageHeader.vue";
import SubtitleFormatTabs from "@/components/SubtitleFormatTabs.vue";
import SubtitleEditor from "@/components/SubtitleEditor.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import EmptyState from "@/components/EmptyState.vue";
import { useSubtitleStore } from "@/stores/subtitle";
import type { SubtitleFormat } from "@/types/subtitle";
import { useResultStore } from "@/stores/result";
import type { FileInfo } from "@/types/result";
import { usePreferencesStore } from "@/stores/preferences";

const props = defineProps<{ taskId: string }>();
const taskId = computed(() => props.taskId);
const taskIdValue = computed(() => taskId.value);

const sub = useSubtitleStore();
const result = useResultStore();
const prefs = usePreferencesStore();

const langSelection = ref(sub.lang || prefs.preferredLang);
const formatSelection = ref<SubtitleFormat>(sub.format);

const langOptions = computed(() => result.manifest?.available_files ?? []);
const manifestNotReady = computed(() => {
  const status = (result.manifest as any)?.task_status as string | undefined;
  return Boolean(status && String(status).toUpperCase() !== "SUCCESS");
});
const noSubtitles = computed(() => !manifestNotReady.value && langOptions.value.length === 0);

const editorModel = computed({
  get: () => sub.content,
  set: (v: string) => sub.setContent(v),
});

const loading = computed(() => result.loading || sub.loading);

function pickInitialFormat(file: FileInfo | undefined, preferred: SubtitleFormat): SubtitleFormat {
  const hasAss = !!file?.ass;
  const hasSrt = !!file?.srt;
  if (preferred === "ass" && hasAss) return "ass";
  if (preferred === "srt" && hasSrt) return "srt";
  if (hasAss) return "ass";
  if (hasSrt) return "srt";
  // Fallback: keep a deterministic choice (API may still 404, but manifest should normally include at least one).
  return preferred;
}

function formatAvailableForLang(lang: string, format: SubtitleFormat): boolean {
  const f = langOptions.value.find((x) => x.lang === lang);
  return format === "ass" ? !!f?.ass : !!f?.srt;
}

async function initForTask(nextTaskId: string) {
  // Ensure store state does not leak across tasks.
  sub.resetForTask(nextTaskId);
  await result.fetchManifest(nextTaskId);

  const options = langOptions.value;
  if (manifestNotReady.value || options.length === 0) return;
  const preferredLang = prefs.preferredLang;
  const initialLang = options.find((o) => o.lang === preferredLang)?.lang ?? options[0]?.lang ?? preferredLang;
  const file = options.find((o) => o.lang === initialLang);
  const initialFormat = pickInitialFormat(file, sub.format);

  langSelection.value = initialLang;
  formatSelection.value = initialFormat;

  await sub.fetchSubtitle(nextTaskId, initialLang, initialFormat);
  prefs.setPreferredLang(initialLang);
}

function confirmDiscardIfDirty(): boolean {
  if (!sub.isDirty) return true;
  return window.confirm("You have unsaved changes. Discard them and leave this page?");
}

onBeforeRouteLeave(() => confirmDiscardIfDirty());
onBeforeRouteUpdate(() => confirmDiscardIfDirty());

watch(
  taskId,
  async (next) => {
    if (!next) return;
    await initForTask(next);
  },
  { immediate: true }
);

async function save() {
  await sub.updateSubtitle(taskId.value, sub.lang, sub.format, sub.content);
}

async function onLanguageChange() {
  const next = langSelection.value;
  if (next === sub.lang) return;

  if (sub.isDirty) {
    const ok = window.confirm("You have unsaved changes. Discard them and switch language?");
    if (!ok) {
      langSelection.value = sub.lang;
      return;
    }
  }

  const nextFormat = formatAvailableForLang(next, sub.format)
    ? sub.format
    : pickInitialFormat(langOptions.value.find((x) => x.lang === next), sub.format);

  formatSelection.value = nextFormat;
  prefs.setPreferredLang(next);
  await sub.fetchSubtitle(taskId.value, next, nextFormat);
}

async function onFormatChange(next: SubtitleFormat) {
  if (next === sub.format) return;

  if (!formatAvailableForLang(sub.lang, next)) {
    window.alert(`No ${next.toUpperCase()} subtitle available for language: ${sub.lang}`);
    formatSelection.value = sub.format;
    return;
  }

  if (sub.isDirty) {
    const ok = window.confirm("You have unsaved changes. Discard them and switch format?");
    if (!ok) {
      formatSelection.value = sub.format;
      return;
    }
  }

  formatSelection.value = next;
  await sub.fetchSubtitle(taskId.value, sub.lang, next);
}
</script>
