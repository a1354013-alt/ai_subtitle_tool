<template>
  <div class="bar" role="progressbar" :aria-valuenow="value" aria-valuemin="0" aria-valuemax="100">
    <div class="fill" :style="{ width: `${clamped}%` }" />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ value: number }>();
const clamped = computed(() => Math.max(0, Math.min(100, props.value)));
</script>

<style scoped>
.bar {
  width: 100%;
  height: 10px;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 999px;
  overflow: hidden;
}
.fill {
  height: 100%;
  background: linear-gradient(90deg, rgba(110, 168, 254, 0.9), rgba(45, 212, 191, 0.9));
}
</style>

