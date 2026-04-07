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
        <div class="label">Progress</div>
        <div class="mono">{{ progress }}%</div>
      </div>
      <div style="margin-top: 10px">
        <ProgressBar :value="progress" />
      </div>

      <div v-if="message" class="msg">{{ message }}</div>
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
  color: var(--muted);
}
</style>

