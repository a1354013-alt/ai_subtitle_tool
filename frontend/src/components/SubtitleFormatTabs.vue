<template>
  <div class="tabs">
    <button class="tab" :class="{ active: modelValue === 'ass' }" @click="$emit('update:modelValue', 'ass')">
      ASS
    </button>
    <button class="tab" :class="{ active: modelValue === 'srt' }" @click="$emit('update:modelValue', 'srt')">
      SRT
    </button>
  </div>
</template>

<script setup lang="ts">
import type { SubtitleFormat } from "@/types/subtitle";

defineProps<{ modelValue: SubtitleFormat }>();
defineEmits<{ (e: "update:modelValue", v: SubtitleFormat): void }>();
</script>

<style scoped>
.tabs {
  display: inline-flex;
  gap: 8px;
  padding: 6px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
}
.tab {
  border: 1px solid transparent;
  background: transparent;
  color: var(--color-muted);
  padding: 8px 10px;
  border-radius: 12px;
  cursor: pointer;
  font-weight: 700;
  font-size: 12px;
}
.tab.active {
  color: var(--color-text);
  border-color: rgba(110, 168, 254, 0.45);
  background: rgba(110, 168, 254, 0.12);
}
</style>

