<template>
  <div>
    <PageHeader :title="$t('editor.title')" :subtitle="$t('editor.subtitle')" />

    <ErrorAlert v-if="sub.error" :error="sub.error" />

    <EmptyState
      v-if="!loading && manifestNotReady"
      :title="$t('editor.notReadyTitle')"
      :description="$t('editor.notReadyDescription')"
    >
      <RouterLink class="btn primary" :to="{ name: 'task', params: { taskId: taskIdValue } }">
        {{ $t('common.goToStatus') }}
      </RouterLink>
    </EmptyState>

    <EmptyState
      v-else-if="!loading && noSubtitles"
      :title="$t('editor.emptyTitle')"
      :description="$t('editor.emptyDescription')"
    >
      <RouterLink class="btn primary" :to="{ name: 'downloads', params: { taskId: taskIdValue } }">
        {{ $t('common.goToDownloads') }}
      </RouterLink>
    </EmptyState>

    <div
      v-else
      class="row"
      style="align-items: center; justify-content: space-between; margin-bottom: 12px"
    >
      <div class="pill">
        <span>{{ $t('editor.taskLabel') }}</span>
        <code class="mono">{{ taskIdValue }}</code>
      </div>

      <div class="row" style="align-items: center">
        <div class="pill" style="margin-right: 8px">
          <span>{{ $t('editor.editingLabel') }}</span>
          <code class="mono">{{ sub.lang }} / {{ sub.format.toUpperCase() }}</code>
        </div>

        <div class="pill">
          <span>{{ $t('editor.languageLabel') }}</span>
          <select class="select" style="width: 220px" v-model="langSelection" @change="onLanguageChange">
            <option v-for="f in langOptions" :key="f.lang" :value="f.lang">{{ f.display_name }}</option>
          </select>
        </div>

        <SubtitleFormatTabs :model-value="formatSelection" @update:modelValue="onFormatChange" />

        <RouterLink class="btn" :to="{ name: 'downloads', params: { taskId: taskIdValue } }">
          {{ $t('editor.download') }}
        </RouterLink>
      </div>
    </div>

    <LoadingBlock v-if="loading" :title="$t('common.loading')" :description="$t('editor.fetchingContent')" />

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
import { useI18n } from "vue-i18n";
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
const { t } = useI18n();
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
  return preferred;
}

function formatAvailableForLang(lang: string, format: SubtitleFormat): boolean {
  const f = langOptions.value.find((x) => x.lang === lang);
  return format === "ass" ? !!f?.ass : !!f?.srt;
}

async function initForTask(nextTaskId: string) {
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
  return window.confirm(t("editor.unsavedLeave"));
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
    const ok = window.confirm(t("editor.unsavedLanguage"));
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
    window.alert(t("editor.formatUnavailable", { format: next.toUpperCase(), lang: sub.lang }));
    formatSelection.value = sub.format;
    return;
  }

  if (sub.isDirty) {
    const ok = window.confirm(t("editor.unsavedFormat"));
    if (!ok) {
      formatSelection.value = sub.format;
      return;
    }
  }

  formatSelection.value = next;
  await sub.fetchSubtitle(taskId.value, sub.lang, next);
}
</script>
