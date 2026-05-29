<template>
  <div class="card">
    <div class="card-inner">
      <form @submit.prevent="onSubmit">
        <div class="row">
          <div class="col">
            <div class="label">{{ $t('upload.selectVideo') }}</div>
            <input class="input" type="file" accept=".mp4,.mkv,.avi,.mov" @change="onFileChange" />
            <div class="help">Accepted: mp4 / mkv / avi / mov (final validation is done by ffprobe).</div>
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
import { ref } from "vue";
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

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "(same origin)";

const MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024; // 2GB

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const selected = input.files?.[0] ?? null;
  if (selected && selected.size > MAX_FILE_SIZE) {
    window.alert(`File too large. Maximum size: 2GB`);
    input.value = ""; // Reset
    file.value = null;
    return;
  }
  file.value = selected;
}

async function onSubmit() {
  if (!file.value) return;
  const fd = new FormData();
  fd.append("file", file.value);
  fd.append("target_langs", targetLangs.value);
  fd.append("subtitle_format", subtitleFormat.value);
  fd.append("burn_subtitles", String(burnSubtitles.value));
  fd.append("remove_silence", String(removeSilence.value));
  fd.append("parallel", String(parallel.value));
  emit("submit", fd);
}
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
