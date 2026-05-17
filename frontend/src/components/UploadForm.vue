<template>
  <div class="card">
    <div class="card-inner">
      <form @submit.prevent="onSubmit">
        <div class="row">
          <div class="col">
            <div class="label">{{ $t('upload.selectVideo') }}</div>
            <input class="input" type="file" accept=".mp4,.mkv,.avi,.mov" @change="onFileChange" />
            <div class="help">
              Supported: {{ config.supportedExtensions.join(", ") }}. Max {{ config.maxUploadSizeMb }}MB.
              Final validation is done by ffprobe.
            </div>
            <div v-if="validationError" class="task-error text-danger">{{ validationError }}</div>
          </div>

          <div class="col">
            <div class="label">{{ $t('upload.targetLanguages') }}</div>
            <input v-model="targetLangs" class="input" type="text" placeholder="Traditional Chinese" />
            <div class="help">Comma-separated languages, e.g. <code class="mono">Traditional Chinese, English</code>.</div>
          </div>
        </div>

        <div class="row" style="margin-top: 12px">
          <div class="col">
            <div class="label">{{ $t('upload.subtitleFormat') }}</div>
            <select v-model="subtitleFormat" class="select">
              <option value="ass">ass</option>
              <option value="srt">srt</option>
            </select>
          </div>

          <div class="col">
            <div class="label">{{ $t('upload.burnSubtitles') }}</div>
            <label class="check">
              <input v-model="burnSubtitles" type="checkbox" />
              <span>Burn subtitles into final.mp4</span>
            </label>
          </div>

          <div class="col">
            <div class="label">{{ $t('upload.removeSilence') }}</div>
            <label class="check">
              <input v-model="removeSilence" type="checkbox" />
              <span>Remove silent parts (may change timings)</span>
            </label>
          </div>

          <div class="col">
            <div class="label">{{ $t('upload.parallel') }}</div>
            <label class="check">
              <input v-model="parallel" type="checkbox" />
              <span>Parallel segments (recommended for longer videos)</span>
            </label>
          </div>
        </div>

        <div class="divider" />

        <div class="row" style="align-items: center; justify-content: space-between">
          <div class="pill">
            <span>API Base URL</span>
            <code class="mono">{{ apiBaseUrl }}</code>
          </div>
          <button class="btn primary" type="submit" :disabled="props.submitting || !file">
            {{ props.submitting ? 'Uploading...' : $t('upload.generate') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { getAppConfig } from "@/api/config";
import type { AppConfig } from "@/types/api";
import type { SubtitleFormat } from "@/types/subtitle";

const emit = defineEmits<{
  (e: "submit", payload: FormData): void;
}>();

const file = ref<File | null>(null);
const props = withDefaults(
  defineProps<{
    submitting?: boolean;
  }>(),
  { submitting: false }
);

const targetLangs = ref("Traditional Chinese");
const subtitleFormat = ref<SubtitleFormat>("ass");
const burnSubtitles = ref(true);
const removeSilence = ref(false);
const parallel = ref(true);
const validationError = ref("");
const config = ref<AppConfig>({
  maxUploadSizeMb: 2048,
  maxBatchFiles: 20,
  supportedExtensions: [".mp4", ".mkv", ".avi", ".mov"],
  batchUploadEnabled: true,
  subtitleFormats: ["srt", "ass", "vtt"],
});

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "(same origin)";

function validateSelectedFile(selected: File | null): string {
  if (!selected) return "";
  const extension = selected.name.includes(".") ? `.${selected.name.split(".").pop()!.toLowerCase()}` : "";
  if (!extension || !config.value.supportedExtensions.includes(extension)) {
    return `Unsupported file format: ${selected.name}. Supported formats: ${config.value.supportedExtensions.join(", ")}.`;
  }
  if (selected.size <= 0) {
    return `Empty files cannot be uploaded: ${selected.name}.`;
  }
  const maxBytes = config.value.maxUploadSizeMb * 1024 * 1024;
  if (selected.size > maxBytes) {
    return `${selected.name} exceeds the ${config.value.maxUploadSizeMb}MB upload limit.`;
  }
  return "";
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const selected = input.files?.[0] ?? null;
  validationError.value = validateSelectedFile(selected);
  if (validationError.value) {
    input.value = "";
    file.value = null;
    return;
  }
  file.value = selected;
}

async function onSubmit() {
  validationError.value = validateSelectedFile(file.value);
  if (!file.value || validationError.value) return;
  const fd = new FormData();
  fd.append("file", file.value);
  fd.append("target_langs", targetLangs.value);
  fd.append("subtitle_format", subtitleFormat.value);
  fd.append("burn_subtitles", String(burnSubtitles.value));
  fd.append("remove_silence", String(removeSilence.value));
  fd.append("parallel", String(parallel.value));
  emit("submit", fd);
}

onMounted(async () => {
  try {
    config.value = await getAppConfig();
  } catch {
    // Keep built-in defaults when the config endpoint is temporarily unavailable.
  }
});
</script>

<style scoped>
.check {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  color: var(--color-muted);
}
</style>
