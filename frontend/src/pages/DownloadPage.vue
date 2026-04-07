<template>
  <div>
    <PageHeader title="下載結果" subtitle="此頁只負責下載已存在的結果，不會做任何隱性背景工作或觸發影片重建。" />

    <ErrorAlert v-if="res.error" :error="res.error" />
    <LoadingBlock v-if="res.loading" title="Loading manifest..." description="正在讀取結果清單" />

    <template v-else>
      <div class="row" style="align-items: center; justify-content: space-between; margin-bottom: 12px">
        <div class="pill">
          <span>Task</span>
          <code class="mono">{{ taskId }}</code>
        </div>
        <RouterLink class="btn" :to="{ name: 'task', params: { taskId } }">回到狀態</RouterLink>
      </div>

      <div class="row" style="margin-bottom: 12px">
        <div class="col card">
          <div class="card-inner">
            <div class="label">下載語言（字幕用）</div>
            <select class="select" v-model="selectedLang" @change="persistLang">
              <option v-for="f in files" :key="f.lang" :value="f.lang">{{ f.display_name }}</option>
            </select>
            <div class="help">
              下載字幕需要同時指定 <code class="mono">language + format</code>；此選項只影響下載 URL，不會觸發任何重建或背景工作。
            </div>
          </div>
        </div>
      </div>

      <EmptyState
        v-if="!manifest"
        title="尚無結果"
        description="目前沒有可用的 manifest。若任務尚未成功完成，請回到狀態頁等待。"
      >
        <RouterLink class="btn primary" :to="{ name: 'task', params: { taskId } }">回到狀態</RouterLink>
      </EmptyState>

      <DownloadList v-else :items="downloadItems" />

      <div v-if="manifest && !manifest.has_video" class="card" style="margin-top: 12px">
        <div class="card-inner">
          <div class="label">注意</div>
          <div class="help">
            <div>
              <strong>final.mp4 不存在</strong>：可能是任務尚未完成，或你曾在字幕編輯後更新了字幕（後端可能會刪除舊的 final.mp4 以避免舊字幕被誤用）。
            </div>
            <div style="margin-top: 6px">
              此頁只負責下載已存在的結果：不會也不應該隱性重建影片。若要套用新字幕到影片，請重新建立任務（或使用未來的明確重建/燒錄流程）。
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import PageHeader from "@/components/PageHeader.vue";
import DownloadList from "@/components/DownloadList.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import EmptyState from "@/components/EmptyState.vue";
import { useResultStore } from "@/stores/result";
import type { DownloadItem } from "@/types/result";
import { buildDownloadUrl } from "@/api/results";
import { setPreferredLang, getPreferredLang } from "@/api/subtitles";

const props = defineProps<{ taskId: string }>();
const taskId = props.taskId;

const res = useResultStore();
const selectedLang = ref(getPreferredLang());

const manifest = computed(() => res.manifest);
const files = computed(() => manifest.value?.available_files ?? []);

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
  setPreferredLang(selectedLang.value);
}

const downloadItems = computed<DownloadItem[]>(() => {
  if (!manifest.value) return [];
  const items: DownloadItem[] = [];

  items.push({
    key: "video",
    label: "Final Video (final.mp4)",
    description: "下載已存在的 final video（若不存在會顯示不可下載）。",
    available: manifest.value.has_video,
    url: manifest.value.has_video ? buildDownloadUrl(taskId) : undefined,
  });

  const langInfo = files.value.find((f) => f.lang === selectedLang.value);
  const hasAss = Boolean(langInfo?.ass);
  const hasSrt = Boolean(langInfo?.srt);

  items.push({
    key: "ass",
    label: `Subtitle (ASS) - ${selectedLang.value}`,
    available: hasAss,
    url: hasAss ? buildDownloadUrl(taskId, "ass", selectedLang.value) : undefined,
  });
  items.push({
    key: "srt",
    label: `Subtitle (SRT) - ${selectedLang.value}`,
    available: hasSrt,
    url: hasSrt ? buildDownloadUrl(taskId, "srt", selectedLang.value) : undefined,
  });

  return items;
});

onMounted(async () => {
  await res.fetchManifest(taskId);
});
</script>
