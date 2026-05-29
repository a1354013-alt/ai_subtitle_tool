<template>
  <div>
    <PageHeader
      :title="$t('task.status')"
      subtitle="This page polls the backend for task progress. Polling is managed by the store and stops on terminal status."
    />

    <ErrorAlert v-if="task.error" :error="task.error" />

    <TaskProgressCard
      :task-id="taskId"
      :status="task.status"
      :progress="task.progress"
      :message="task.message"
      :warnings="task.warnings"
    />

    <div class="row actions">
      <RouterLink class="btn" :to="{ name: 'home' }">{{ $t('navbar.home') }}</RouterLink>
      <RouterLink
        v-if="isSuccess"
        class="btn primary"
        :to="{ name: 'subtitles', params: { taskId } }"
      >
        {{ $t('editor.title') }}
      </RouterLink>
      <RouterLink
        v-if="isSuccess"
        class="btn primary"
        :to="{ name: 'downloads', params: { taskId } }"
      >
        {{ $t('editor.download') }}
      </RouterLink>

      <div v-if="isTerminal" class="report-actions">
        <button class="btn secondary" @click="exportReport('md')">Export MD Report</button>
        <button class="btn secondary" @click="exportReport('pdf')">Export PDF Report</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from "vue";
import { RouterLink } from "vue-router";
import PageHeader from "@/components/PageHeader.vue";
import TaskProgressCard from "@/components/TaskProgressCard.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import { useTaskStore } from "@/stores/task";

const props = defineProps<{ taskId: string }>();
const taskId = computed(() => props.taskId);

const task = useTaskStore();
const isSuccess = computed(() => String(task.status).toUpperCase() === "SUCCESS");
const isTerminal = computed(() => ["SUCCESS", "FAILURE"].includes(String(task.status).toUpperCase()));

import { buildApiUrl } from "@/api/client";

function exportReport(format: 'md' | 'pdf') {
  const url = buildApiUrl(`/api/tasks/${taskId.value}/report?format=${format}`);
  window.open(url, "_blank");
}

watch(
  taskId,
  (next) => {
    if (!next) return;
    void task.startPolling(next);
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  task.stopPolling();
});
</script>

<style scoped>
.actions {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.report-actions {
  display: flex;
  gap: 10px;
}

.btn.secondary {
  background: rgba(255, 255, 255, 0.1);
  color: white;
}

.btn.secondary:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>
