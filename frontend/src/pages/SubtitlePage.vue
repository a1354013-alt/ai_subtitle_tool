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

const editorContent = ref("");
const langSelection = ref(sub.lang || getPreferredLang());
const formatSelection = ref<SubtitleFormat>(sub.format);

const langOptions = computed(() => result.manifest?.available_files ?? []);

const ready = ref(false);

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

// UI selection 同步（只做同步，不做控制/rollback）
watch(
  () => sub.lang,
  (v) => {
    if (langSelection.value !== v) langSelection.value = v;
  }
);
watch(
  () => sub.format,
  (v) => {
    if (formatSelection.value !== v) formatSelection.value = v;
  }
);

watch(
  () => [ready.value, sub.lang, sub.format] as const,
  async ([isReady, lang, fmt]) => {
    if (!isReady) return;
    await sub.fetchSubtitle(taskId, lang, fmt);
  },
  { immediate: true }
);

onMounted(async () => {
  await result.fetchManifest(taskId);
  const options = langOptions.value;
  const preferred = getPreferredLang();
  const initialLang = options.find((o) => o.lang === preferred)?.lang ?? options[0]?.lang ?? preferred;

  // 只做初始化：不在 onMounted 主動 fetchSubtitle（由 watch(ready/lang/format) 單一入口觸發）
  sub.setLang(initialLang);
  sub.setFormat(sub.format); // 保持目前 format
  langSelection.value = initialLang;
  formatSelection.value = sub.format;
  setPreferredLang(initialLang);
  ready.value = true;
});

async function save() {
  await sub.updateSubtitle(taskId, sub.lang, sub.format, editorContent.value);
}

function onLanguageChange() {
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

function onFormatChange(next: SubtitleFormat) {
  if (next === sub.format) return;
  if (sub.isDirty) {
    const ok = window.confirm("你有尚未儲存的變更。切換格式將會捨棄目前未儲存內容。要繼續嗎？");
    if (!ok) {
      formatSelection.value = sub.format;
      return;
    }
  }
  sub.setFormat(next);
}
</script>
