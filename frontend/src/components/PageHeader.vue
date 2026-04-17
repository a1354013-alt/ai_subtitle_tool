<template>
  <div class="head">
    <div class="h1">{{ title }}</div>
    <div v-if="subtitle" class="h2">{{ subtitle }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  subtitle?: string;
}>();
</script>

<style scoped>
.head {
  margin: 6px 0 18px;
}
.h1 {
  font-size: 20px;
  font-weight: 800;
}
.h2 {
  margin-top: 8px;
  font-size: 13px;
  color: var(--color-muted);
  max-width: 72ch;
}
</style>

