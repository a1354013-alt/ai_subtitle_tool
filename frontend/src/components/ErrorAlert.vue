<template>
  <div class="alert card">
    <div class="card-inner">
      <div class="title">{{ title }}</div>
      <div class="msg">{{ message }}</div>
      <div v-if="detail" class="detail mono">{{ detail }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { APIError } from "@/types/api";

const props = defineProps<{
  title?: string;
  error: APIError | null;
}>();

const title = props.title ?? "發生錯誤";
const message = props.error?.message ?? "Unknown error";
const detail = typeof props.error?.detail === "string" ? props.error?.detail : "";
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
.detail {
  margin-top: 10px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
  white-space: pre-wrap;
}
</style>

