<template>
  <div class="card">
    <div class="card-inner">
      <div class="row top">
        <div>
          <div class="label">Task ID</div>
          <div class="mono id">{{ taskId }}</div>
        </div>
        <StatusBadge :status="status" />
      </div>

      <div class="divider" />

      <div class="row" style="align-items: center; justify-content: space-between">
        <div class="label">{{ $t('task.progress') }}</div>
        <div class="mono">{{ progress }}%</div>
      </div>
      <div style="margin-top: 10px">
        <ProgressBar :value="progress" />
      </div>

      <div v-if="message" class="msg">{{ message }}</div>

      <div v-if="warnings.length" class="warn">
        <div class="warn-title">Non-fatal warnings</div>
        <ul class="warn-list">
          <li v-for="(w, i) in warnings" :key="i">{{ w }}</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import ProgressBar from "@/components/ProgressBar.vue";
import StatusBadge from "@/components/StatusBadge.vue";

defineProps<{
  taskId: string;
  status: string;
  progress: number;
  message?: string;
  warnings: string[];
}>();
</script>

<style scoped>
.top {
  align-items: center;
  justify-content: space-between;
}
.id {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.9);
}
.msg {
  margin-top: 12px;
  font-size: 13px;
  color: var(--color-muted);
}
.warn {
  margin-top: 12px;
  padding: 12px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 193, 7, 0.35);
  background: rgba(255, 193, 7, 0.08);
}
.warn-title {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.2px;
}
.warn-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: rgba(255, 255, 255, 0.9);
  font-size: 13px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
