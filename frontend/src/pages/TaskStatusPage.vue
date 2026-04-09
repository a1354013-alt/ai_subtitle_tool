<template>
  <div>
    <PageHeader
      title="Task Status"
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
      <RouterLink class="btn" :to="{ name: 'home' }">Back</RouterLink>
      <RouterLink
        v-if="isSuccess"
        class="btn primary"
        :to="{ name: 'subtitles', params: { taskId } }"
      >
        Subtitles
      </RouterLink>
      <RouterLink
        v-if="isSuccess"
        class="btn primary"
        :to="{ name: 'downloads', params: { taskId } }"
      >
        Downloads
      </RouterLink>
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
}
</style>
