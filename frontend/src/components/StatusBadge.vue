<template>
  <span class="badge" :class="tone">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{ status: string }>();
const { t } = useI18n();

const tone = computed(() => {
  const s = props.status.toUpperCase();
  if (s === "SUCCESS") return "ok";
  if (s === "FAILURE" || s === "CANCELED") return "bad";
  if (s === "PROCESSING") return "warn";
  return "neutral";
});

const label = computed(() => {
  const s = props.status.toUpperCase();
  if (s === "SUCCESS") return t("task.success");
  if (s === "FAILURE") return t("task.failure");
  if (s === "CANCELED") return t("task.canceled");
  if (s === "PROCESSING") return t("task.processing");
  return t("task.pending");
});
</script>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-muted);
}
.badge.ok {
  border-color: rgba(45, 212, 191, 0.45);
  background: rgba(45, 212, 191, 0.12);
  color: #a9fff4;
}
.badge.warn {
  border-color: rgba(251, 191, 36, 0.45);
  background: rgba(251, 191, 36, 0.12);
  color: #ffe4a3;
}
.badge.bad {
  border-color: rgba(255, 107, 107, 0.45);
  background: rgba(255, 107, 107, 0.12);
  color: #ffd0d0;
}
</style>
