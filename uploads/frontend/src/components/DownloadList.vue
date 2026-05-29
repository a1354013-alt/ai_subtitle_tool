<template>
  <div class="card">
    <div class="card-inner">
      <div class="label">{{ $t('download.title') }}</div>
      <div v-if="items.length === 0" class="help">No downloadable items.</div>

      <div class="list">
        <div v-for="it in items" :key="it.key" class="item">
          <div class="meta">
            <div class="name">{{ it.label }}</div>
            <div v-if="it.description" class="desc">{{ it.description }}</div>
          </div>
          <div>
            <a v-if="it.available && it.url" class="btn primary" :href="it.url">{{ $t('download.button') }}</a>
            <button v-else class="btn" disabled>Not available</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DownloadItem } from "@/types/result";

defineProps<{ items: DownloadItem[] }>();
</script>

<style scoped>
.list {
  margin-top: 10px;
  display: grid;
  gap: 10px;
}
.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.10);
  background: rgba(255, 255, 255, 0.04);
}
.name {
  font-weight: 800;
}
.desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-muted);
}
</style>
