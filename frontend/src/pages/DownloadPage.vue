<template>
  <div>
    <PageHeader :title="$t('downloads.title')" :subtitle="$t('downloads.subtitle')" />

    <ErrorAlert v-if="res.error" :error="res.error" />
    <LoadingBlock v-if="res.loading" :title="$t('common.loading')" :description="$t('downloads.fetching')" />

    <template v-else>
      <div class="row" style="align-items: center; justify-content: space-between; margin-bottom: 12px">
        <div class="pill">
          <span>{{ $t('editor.taskLabel') }}</span>
          <code class="mono">{{ taskId }}</code>
        </div>
        <RouterLink class="btn" :to="{ name: 'task', params: { taskId } }">{{ $t('task.status') }}</RouterLink>
      </div>

      <div v-if="manifest && isSuccessManifest" class="row" style="margin-bottom: 12px">
        <div class="col card">
          <div class="card-inner">
            <div class="label">{{ $t('downloads.languageLabel') }}</div>
            <select class="select" v-model="selectedLang" @change="persistLang">
              <option v-for="f in files" :key="f.lang" :value="f.lang">{{ f.display_name }}</option>
            </select>
            <div class="help">{{ $t('downloads.languageHelp') }}</div>
          </div>
        </div>
      </div>

      <EmptyState v-if="!manifest" :title="$t('downloads.noManifestTitle')" :description="$t('downloads.noManifestDescription')">
        <RouterLink class="btn primary" :to="{ name: 'task', params: { taskId } }">{{ $t('common.goToStatus') }}</RouterLink>
      </EmptyState>

      <EmptyState
        v-else-if="!isSuccessManifest"
        :title="$t('downloads.notReadyTitle')"
        :description="$t('downloads.notReadyDescription')"
      >
        <RouterLink class="btn primary" :to="{ name: 'task', params: { taskId } }">{{ $t('common.goToStatus') }}</RouterLink>
      </EmptyState>

      <DownloadList v-else :items="downloadItems" />

      <div v-if="manifest && !manifest.has_video" class="card" style="margin-top: 12px">
        <div class="card-inner">
          <div class="label">{{ $t('downloads.noteTitle') }}</div>
          <div class="help">
            <div>
              <strong>{{ $t('downloads.finalVideoMissingTitle') }}</strong>
              {{ $t('downloads.finalVideoMissingBody') }}
            </div>
            <div style="margin-top: 6px">
              {{ $t('downloads.noAutoRebuild') }}
            </div>
            <div v-if="manifest && isSuccessManifest" style="margin-top: 10px">
              <button class="btn primary" :disabled="rebuilding || !selectedLang" @click="onRebuildFinal">
                {{ rebuilding ? $t('common.loading') : $t('editor.rebuild') }}
              </button>
              <div class="help" style="margin-top: 6px">
                {{ $t('downloads.rebuildHelp') }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import PageHeader from "@/components/PageHeader.vue";
import DownloadList from "@/components/DownloadList.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import EmptyState from "@/components/EmptyState.vue";
import { useResultStore } from "@/stores/result";
import type { DownloadItem } from "@/types/result";
import { buildDownloadUrl } from "@/api/results";
import { usePreferencesStore } from "@/stores/preferences";
import { rebuildFinalVideo } from "@/api/tasks";

const props = defineProps<{ taskId: string }>();
const { t } = useI18n();
const taskId = computed(() => props.taskId);
const router = useRouter();

const res = useResultStore();
const prefs = usePreferencesStore();
const selectedLang = ref(prefs.preferredLang);

const manifest = computed(() => res.manifest);
const files = computed(() => manifest.value?.available_files ?? []);
const isSuccessManifest = computed(() => {
  const s = manifest.value?.task_status;
  if (!s) return true;
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

const rebuilding = ref(false);

async function onRebuildFinal() {
  if (!selectedLang.value) return;
  rebuilding.value = true;
  try {
    const langInfo = files.value.find((f) => f.lang === selectedLang.value);
    const format = langInfo?.ass ? "ass" : "srt";
    await rebuildFinalVideo(taskId.value, selectedLang.value, format);
    await router.push({ name: "task", params: { taskId: taskId.value } });
  } finally {
    rebuilding.value = false;
  }
}

const downloadItems = computed<DownloadItem[]>(() => {
  if (!manifest.value) return [];
  const items: DownloadItem[] = [];

  items.push({
    key: "video",
    label: t("downloads.finalVideoLabel"),
    description: t("downloads.finalVideoDescription"),
    available: manifest.value.has_video,
    url: manifest.value.has_video ? buildDownloadUrl(taskId.value) : undefined,
  });

  const langInfo = files.value.find((f) => f.lang === selectedLang.value);
  const hasAss = Boolean(langInfo?.ass);
  const hasSrt = Boolean(langInfo?.srt);

  items.push({
    key: "ass",
    label: t("downloads.subtitleAssLabel", { lang: selectedLang.value }),
    available: hasAss,
    url: hasAss ? buildDownloadUrl(taskId.value, "ass", selectedLang.value) : undefined,
  });

  items.push({
    key: "srt",
    label: t("downloads.subtitleSrtLabel", { lang: selectedLang.value }),
    available: hasSrt,
    url: hasSrt ? buildDownloadUrl(taskId.value, "srt", selectedLang.value) : undefined,
  });

  items.push({
    key: "vtt",
    label: t("downloads.subtitleVttLabel", { lang: selectedLang.value }),
    description: t("downloads.subtitleVttDescription"),
    available: hasSrt,
    url: hasSrt ? buildDownloadUrl(taskId.value, "vtt", selectedLang.value) : undefined,
  });

  return items;
});

watch(
  taskId,
  async (next) => {
    if (!next) return;
    selectedLang.value = prefs.preferredLang;
    await res.fetchManifest(next);
  },
  { immediate: true }
);
</script>
