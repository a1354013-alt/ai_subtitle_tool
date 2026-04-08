<template>
  <div>
    <PageHeader
      title="Subtitles"
      subtitle="Edit subtitle files (ASS/SRT). Editing only updates the subtitle file; it does not rebuild/burn the final video."
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

        <RouterLink class="btn" :to="{ name: 'downloads', params: { taskId } }">Downloads</RouterLink>
      </div>
    </div>

    <LoadingBlock v-if="loading" title="Loading subtitle..." description="Fetching subtitle content." />

    <SubtitleEditor
      v-else
      v-model="editorModel"
      :dirty="sub.isDirty"
      :saving="sub.saving"
      :last-saved-at="sub.lastSavedAt"
      @save="save"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
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

const langSelection = ref(sub.lang || getPreferredLang());
const formatSelection = ref<SubtitleFormat>(sub.format);

const langOptions = computed(() => result.manifest?.available_files ?? []);

const editorModel = computed({
  get: () => sub.content,
  set: (v: string) => sub.setContent(v),
});

const loading = computed(() => result.loading || sub.loading);

onMounted(async () => {
  await result.fetchManifest(taskId);

  const options = langOptions.value;
  const preferred = getPreferredLang();
  const initialLang = options.find((o) => o.lang === preferred)?.lang ?? options[0]?.lang ?? preferred;

  // Initialize explicit selections.
  langSelection.value = initialLang;
  formatSelection.value = sub.format;

  // Load once.
  await sub.fetchSubtitle(taskId, initialLang, sub.format);

  setPreferredLang(initialLang);
});

async function save() {
  await sub.updateSubtitle(taskId, sub.lang, sub.format, sub.content);
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

  setPreferredLang(next);
  await sub.fetchSubtitle(taskId, next, sub.format);
}

async function onFormatChange(next: SubtitleFormat) {
  if (next === sub.format) return;

  if (sub.isDirty) {
    const ok = window.confirm("You have unsaved changes. Discard them and switch format?");
    if (!ok) {
      formatSelection.value = sub.format;
      return;
    }
  }

  formatSelection.value = next;
  await sub.fetchSubtitle(taskId, sub.lang, next);
}
</script>
