<template>
  <div class="card">
    <div class="card-inner">
      <div class="row" style="align-items: center; justify-content: space-between">
        <div>
          <div class="label">Subtitle Content</div>
          <div class="help">
            編輯只會更新字幕檔（ass/srt），<strong>不會自動重建影片</strong>。若要把新字幕套用到影片，需重新建立任務或提供明確的 burn/rebuild 端點。
          </div>
        </div>
        <div class="row" style="align-items: center">
          <span v-if="savedHint" class="pill">已儲存：{{ savedHint }}</span>
          <button class="btn primary" :disabled="saving || !dirty" @click="$emit('save')">
            {{ saving ? "Saving..." : "儲存字幕" }}
          </button>
        </div>
      </div>

      <div style="margin-top: 12px">
        <textarea class="textarea" :value="modelValue" @input="onInput" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  modelValue: string;
  dirty: boolean;
  saving: boolean;
  lastSavedAt?: number | null;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: string): void;
  (e: "save"): void;
}>();

function onInput(e: Event) {
  const ta = e.target as HTMLTextAreaElement;
  emit("update:modelValue", ta.value);
}

const savedHint = computed(() => {
  if (!props.lastSavedAt) return "";
  const d = new Date(props.lastSavedAt);
  return d.toLocaleString();
});
</script>

