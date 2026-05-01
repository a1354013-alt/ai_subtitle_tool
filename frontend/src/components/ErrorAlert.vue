<template>
  <div class="alert card">
    <div class="card-inner">
      <div class="title">❌ {{ titleText }}</div>
      <div class="msg">{{ messageText }}</div>
      <div v-if="suggestionText" class="suggestion">
        <strong>{{ $t('common.suggestion') }}:</strong> {{ suggestionText }}
      </div>
      <div v-if="detailText" class="detail mono">{{ detailText }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { APIError } from "@/types/api";

const props = defineProps<{
  title?: string;
  error: APIError | null;
}>();

const titleText = computed(() => props.title ?? props.error?.error_code ?? "Error");
const messageText = computed(() => props.error?.message ?? "Unknown error");
const suggestionText = computed(() => props.error?.suggestion ?? "");
const detailText = computed(() => (typeof props.error?.detail === "string" ? props.error?.detail : ""));
</script>

<style scoped>
.alert {
  border-color: rgba(255, 107, 107, 0.35);
}
.title {
  font-weight: 800;
  margin-bottom: 8px;
}
.msg {
  color: #ffd0d0;
}
.suggestion {
  margin-top: 10px;
  padding: 8px 12px;
  background: rgba(255, 193, 7, 0.1);
  border-left: 3px solid rgba(255, 193, 7, 0.5);
  border-radius: 4px;
  font-size: 0.875rem;
  color: #ffd700;
}
.detail {
  margin-top: 10px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
  white-space: pre-wrap;
}
</style>
