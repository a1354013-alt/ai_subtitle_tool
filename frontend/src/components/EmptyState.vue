<template>
  <div class="card">
    <div class="card-inner">
      <div class="title">{{ title }}</div>
      <div class="desc">{{ description }}</div>
      <div v-if="$slots.default" class="actions">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    description?: string;
  }>(),
  {
    title: "No data",
    description: "目前沒有可顯示的資料。",
  }
);
</script>

<style scoped>
.title {
  font-weight: 800;
}
.desc {
  margin-top: 8px;
  font-size: 13px;
  color: var(--muted);
}
.actions {
  margin-top: 12px;
}
</style>

