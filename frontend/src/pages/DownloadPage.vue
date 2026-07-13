<template>
  <div>
    <PageHeader
      :title="$t('editor.download')"
      :subtitle="$t('download.subtitle')"
    />

    <ErrorAlert v-if="res.error" :error="res.error" />
    <LoadingBlock v-if="res.loading" :title="$t('common.loading')" :description="$t('download.fetchingFiles')" />

    <template v-else>
      <div class="row" style="align-items: center; justify-content: space-between; margin-bottom: 12px">
        <div class="pill">
          <span>{{ $t('download.task') }}</span>
          <code class="mono">{{ taskId }}</code>
        </div>
        <RouterLink class="btn" :to="{ name: 'task', params: { taskId } }">{{ $t('task.status') }}</RouterLink>
      </div>

      <div v-if="manifest && isSuccessManifest" class="row" style="margin-bottom: 12px">
        <div class="col card">
          <div class="card-inner">
            <div class="label">{{ $t('download.language') }}</div>
            <select class="select" v-model="selectedLang" @change="persistLang">
              <option v-for="f in files" :key="f.lang" :value="f.lang">{{ f.display_name }}</option>
            </select>
            <div class="help">
              {{ $t('download.languageHelp') }}
            </div>
          </div>
        </div>
      </div>

      <EmptyState
        v-if="!manifest"
        :title="$t('download.noManifestTitle')"
        :description="$t('download.noManifestDescription')"
      >
        <RouterLink class="btn primary" :to="{ name: 'task', params: { taskId } }">{{ $t('download.goToStatus') }}</RouterLink>
      </EmptyState>

      <EmptyState
        v-else-if="!isSuccessManifest"
        :title="$t('download.notReadyTitle')"
        :description="$t('download.notReadyDescription')"
      >
        <RouterLink class="btn primary" :to="{ name: 'task', params: { taskId } }">{{ $t('download.goToStatus') }}</RouterLink>
      </EmptyState>

      <DownloadList v-else :items="downloadItems" />

      <div v-if="fallbackMessages.length > 0" class="card" style="margin-top: 12px">
        <div class="card-inner">
          <div class="label">{{ $t('download.translationWarnings') }}</div>
          <ul class="help warning-list">
            <li v-for="message in fallbackMessages" :key="message">{{ message }}</li>
          </ul>
        </div>
      </div>

      <div v-if="showRebuildCard" class="card" style="margin-top: 12px">
        <div class="card-inner">
          <div class="label">{{ rebuildCardTitle }}</div>
          <div class="help">
            <div v-if="!manifest?.has_video">
              <strong>{{ $t('download.missingFinalStrong') }}</strong> {{ $t('download.missingFinalDescription') }}
            </div>
            <div v-else>
              {{ $t('download.rebuildExistingDescription') }}
            </div>
            <div style="margin-top: 8px">
              <label class="label" for="rebuild-format">{{ $t('download.subtitleFormat') }}</label>
              <select id="rebuild-format" class="select" v-model="selectedFormat" style="max-width: 220px">
                <option v-for="format in availableRebuildFormats" :key="format" :value="format">
                  {{ format.toUpperCase() }}
                </option>
              </select>
            </div>
            <div style="margin-top: 10px">
              <button class="btn primary" :disabled="rebuilding || !selectedLang" @click="onRebuildFinal">
                {{ rebuilding ? $t('common.loading') : rebuildCardTitle }}
              </button>
              <div class="help" style="margin-top: 6px">
                {{ $t('download.rebuildHelp') }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="manifest && isSuccessManifest" class="card" style="margin-top: 12px">
        <div class="card-inner">
          <div class="label">{{ $t('download.finalVideoNoteTitle') }}</div>
          <div class="help">{{ $t('download.finalVideoLanguageNote') }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { RouterLink, useRouter } from "vue-router";
import PageHeader from "@/components/PageHeader.vue";
import DownloadList from "@/components/DownloadList.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import EmptyState from "@/components/EmptyState.vue";
import { useResultStore } from "@/stores/result";
import type { DownloadItem } from "@/types/result";
import { buildDownloadPath } from "@/api/results";
import { usePreferencesStore } from "@/stores/preferences";
import { rebuildFinalVideo } from "@/api/tasks";
import type { SubtitleFormat } from "@/types/subtitle";

const props = defineProps<{ taskId: string }>();
const { t } = useI18n();
const taskId = computed(() => props.taskId);
const router = useRouter();

const res = useResultStore();
const prefs = usePreferencesStore();
const selectedLang = ref(prefs.preferredLang);
const selectedFormat = ref<SubtitleFormat>("ass");

const manifest = computed(() => res.manifest);
const files = computed(() => manifest.value?.available_files ?? []);
const selectedFile = computed(() => files.value.find((f) => f.lang === selectedLang.value));
const availableRebuildFormats = computed<SubtitleFormat[]>(() => {
  const formats: SubtitleFormat[] = [];
  if (selectedFile.value?.ass) formats.push("ass");
  if (selectedFile.value?.srt) formats.push("srt");
  return formats;
});
const fallbackMessages = computed(() =>
  files.value
    .filter((f) => f.translated === false)
    .map((f) => t("download.fallbackWarning", { language: f.display_name, reason: f.fallback_reason || t("download.unknownReason") }))
);
const isSuccessManifest = computed(() => {
  const s = manifest.value?.task_status;
  if (!s) return true; // backwards-compat for older manifests
  return String(s).toUpperCase() === "SUCCESS";
});
const showRebuildCard = computed(() => Boolean(manifest.value && isSuccessManifest.value && files.value.length > 0));
const rebuildCardTitle = computed(() =>
  manifest.value?.has_video ? t("download.rebuildFinalVideo") : t("download.generateFinalVideo")
);

watch(
  files,
  (list) => {
    if (list.length === 0) return;
    const exists = list.some((f) => f.lang === selectedLang.value);
    if (!exists) {
      selectedLang.value = list[0].lang;
      persistLang();
    }
    ensureSelectedFormat();
  },
  { immediate: true }
);

function persistLang() {
  prefs.setPreferredLang(selectedLang.value);
  ensureSelectedFormat();
}

function ensureSelectedFormat() {
  if (availableRebuildFormats.value.includes(selectedFormat.value)) return;
  selectedFormat.value = availableRebuildFormats.value[0] ?? "ass";
}

const rebuilding = ref(false);

async function onRebuildFinal() {
  if (!selectedLang.value) return;
  rebuilding.value = true;
  try {
    const langInfo = files.value.find((f) => f.lang === selectedLang.value);
    const format = availableRebuildFormats.value.includes(selectedFormat.value)
      ? selectedFormat.value
      : langInfo?.ass
        ? "ass"
        : "srt";
    const response = await rebuildFinalVideo(taskId.value, selectedLang.value, format);
    await router.push({ name: "task", params: { taskId: response.rebuild_task_id } });
  } catch (e) {
    res.error = e as any;
  } finally {
    rebuilding.value = false;
  }
}

const downloadItems = computed<DownloadItem[]>(() => {
  if (!manifest.value) return [];
  const items: DownloadItem[] = [];

  items.push({
    key: "video",
    label: t("download.finalVideoLabel"),
    description: t("download.finalVideoDescription"),
    available: manifest.value.has_video,
    path: manifest.value.has_video ? buildDownloadPath(taskId.value) : undefined,
  });

  const langInfo = files.value.find((f) => f.lang === selectedLang.value);
  const hasAss = Boolean(langInfo?.ass);
  const hasSrt = Boolean(langInfo?.srt);
  const hasVtt = Boolean(langInfo?.vtt ?? langInfo?.srt);

  items.push({
    key: "ass",
    label: `Subtitle (ASS) - ${selectedLang.value}`,
    description: langInfo?.translated === false ? t("download.translationFailedDescription") : undefined,
    available: hasAss,
    path: hasAss ? buildDownloadPath(taskId.value, "ass", selectedLang.value) : undefined,
  });

  items.push({
    key: "srt",
    label: `Subtitle (SRT) - ${selectedLang.value}`,
    description: langInfo?.translated === false ? t("download.translationFailedDescription") : undefined,
    available: hasSrt,
    path: hasSrt ? buildDownloadPath(taskId.value, "srt", selectedLang.value) : undefined,
  });

  items.push({
    key: "vtt",
    label: `Subtitle (VTT) - ${selectedLang.value}`,
    description: t("download.vttDescription"),
    available: hasVtt,
    path: hasVtt ? buildDownloadPath(taskId.value, "vtt", selectedLang.value) : undefined,
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

<style scoped>
.warning-list {
  margin: 8px 0 0;
  padding-left: 18px;
}
</style>
