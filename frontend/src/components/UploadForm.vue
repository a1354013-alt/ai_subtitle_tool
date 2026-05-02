<template>
  <div class="card">
    <div class="card-inner">
      <form @submit.prevent="onSubmit">
        <div class="row">
          <div class="col">
            <div class="label">{{ $t('upload.selectVideo') }}</div>
            <input class="input" type="file" accept=".mp4,.mkv,.avi,.mov" @change="onFileChange" />
            <div class="help">{{ $t('upload.acceptedFormats') }}</div>
          </div>

          <div class="col">
            <div class="label">{{ $t('upload.targetLanguages') }}</div>
            <input
              v-model="targetLangs"
              class="input"
              type="text"
              :placeholder="$t('upload.targetLanguagesPlaceholder')"
            />
            <div class="help">
              {{ $t('upload.targetLanguagesHelp', { example: 'Traditional Chinese, English' }) }}
            </div>
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
              <span>{{ $t('upload.burnSubtitlesHelp') }}</span>
            </label>
          </div>

          <div class="col">
            <div class="label">{{ $t('upload.removeSilence') }}</div>
            <label class="check">
              <input v-model="removeSilence" type="checkbox" />
              <span>{{ $t('upload.removeSilenceHelp') }}</span>
            </label>
          </div>

          <div class="col">
            <div class="label">{{ $t('upload.parallel') }}</div>
            <label class="check">
              <input v-model="parallel" type="checkbox" />
              <span>{{ $t('upload.parallelHelp') }}</span>
            </label>
          </div>
        </div>

        <div class="divider" />

        <div class="row" style="align-items: center; justify-content: space-between">
          <div class="pill">
            <span>{{ $t('upload.apiBaseUrl') }}</span>
            <code class="mono">{{ apiBaseUrl }}</code>
          </div>
          <button class="btn primary" type="submit" :disabled="props.submitting || !file">
            {{ props.submitting ? $t('upload.uploading') : $t('upload.generate') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import type { SubtitleFormat } from "@/types/subtitle";

const emit = defineEmits<{
  (e: "submit", payload: FormData): void;
}>();

const { t } = useI18n();
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

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? t("upload.sameOrigin");

const MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024;

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const selected = input.files?.[0] ?? null;
  if (selected && selected.size > MAX_FILE_SIZE) {
    window.alert(t("upload.fileTooLarge"));
    input.value = "";
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
