<template>
  <div class="card">
    <div class="card-inner">
      <div class="title">{{ titleText }}</div>
      <div class="desc">{{ descriptionText }}</div>
      <div v-if="$slots.default" class="actions">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
const props = defineProps<{
  title?: string;
  description?: string;
}>();
const titleText = computed(() => props.title ?? t("common.noData"));
const descriptionText = computed(() => props.description ?? t("common.nothingToShowYet"));
</script>

<style scoped>
.title {
  font-weight: 800;
}
.desc {
  margin-top: 8px;
  font-size: 13px;
  color: var(--color-muted);
}
.actions {
  margin-top: 12px;
}
</style>
