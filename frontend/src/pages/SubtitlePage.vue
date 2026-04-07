<template>
  <div>
    <PageHeader
      title="字幕檢視 / 編輯"
      subtitle="切換格式後會讀取對應字幕；儲存只更新字幕檔，不會自動重建影片。"
    />

    <ErrorAlert v-if="sub.error" :error="sub.error" />

    <div class="row" style="align-items: center; justify-content: space-between; margin-bottom: 12px">
      <div class="pill">
        <span>Task</span>
        <code class="mono">{{ taskId }}</code>
      </div>
      <div class="row" style="align-items: center">
        <div class="pill">
          <span>Language</span>
          <select class="select" style="width: 220px" v-model="langSelection" @change="onLangChange">
            <option v-for="f in langOptions" :key="f.lang" :value="f.lang">{{ f.display_name }}</option>
          </select>
        </div>
        <SubtitleFormatTabs v-model="format" />
        <RouterLink class="btn" :to="{ name: 'downloads', params: { taskId } }">前往下載</RouterLink>
      </div>
    </div>

    <LoadingBlock v-if="sub.loading" title="Loading subtitle..." description="正在讀取字幕內容" />

    <SubtitleEditor
      v-else
      v-model="editorContent"
      :dirty="sub.isDirty"
      :saving="sub.saving"
      :last-saved-at="sub.lastSavedAt"
      @save="save"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import PageHeader from "@/components/PageHeader.vue";
import SubtitleFormatTabs from "@/components/SubtitleFormatTabs.vue";
import SubtitleEditor from "@/components/SubtitleEditor.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import { useSubtitleStore } from "@/stores/subtitle";
import type { SubtitleFormat } from "@/types/subtitle";
import { useResultStore } from "@/stores/result";
import { getPreferredLang, setPreferredLang } from "@/api/subtitles";

const props = defineProps<{ taskId: string }>();
const taskId = props.taskId;

const sub = useSubtitleStore();
const result = useResultStore();

const format = computed<SubtitleFormat>({
  get: () => sub.format,
  set: (v) => sub.setFormat(v),
});

const editorContent = ref("");
const langSelection = ref(sub.lang || getPreferredLang());

const langOptions = computed(() => result.manifest?.available_files ?? []);

watch(
  () => sub.content,
  (v) => {
    editorContent.value = v;
  },
  { immediate: true }
);

watch(
  () => editorContent.value,
  (v) => {
    if (v !== sub.content) sub.setContent(v);
  }
);

watch(
  () => sub.format,
  (nextFmt, prevFmt) => {
    if (nextFmt === prevFmt) return;
    if (!sub.isDirty) return;
    const ok = window.confirm("你有尚未儲存的變更。切換格式將會捨棄目前未儲存內容。要繼續嗎？");
    if (!ok) {
      sub.setFormat(prevFmt);
    }
  }
);

watch(
  () => [sub.lang, sub.format] as const,
  async ([lang, fmt]) => {
    await sub.fetchSubtitle(taskId, lang, fmt);
  },
  { deep: false }
);

onMounted(async () => {
  await result.fetchManifest(taskId);
  const options = langOptions.value;
  const preferred = getPreferredLang();
  const initialLang = options.find((o) => o.lang === preferred)?.lang ?? options[0]?.lang ?? preferred;

  sub.setLang(initialLang);
  langSelection.value = initialLang;
  setPreferredLang(initialLang);

  await sub.fetchSubtitle(taskId, sub.lang, sub.format);
});

async function save() {
  await sub.updateSubtitle(taskId, sub.lang, sub.format, editorContent.value);
}

function onLangChange() {
  const next = langSelection.value;
  if (sub.isDirty) {
    const ok = window.confirm("你有尚未儲存的變更。切換語言將會捨棄目前未儲存內容。要繼續嗎？");
    if (!ok) {
      langSelection.value = sub.lang;
      return;
    }
  }
  sub.setLang(next);
  setPreferredLang(next);
}
</script>
