<template>
  <div>
    <PageHeader
      title="任務狀態"
      subtitle="此頁只負責顯示狀態並輪詢；輪詢邏輯集中在 store，任務到終態或離開頁面都會停止輪詢。"
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
      <RouterLink class="btn" :to="{ name: 'home' }">回到上傳</RouterLink>
      <RouterLink v-if="isSuccess" class="btn primary" :to="{ name: 'subtitles', params: { taskId } }">檢視 / 編輯字幕</RouterLink>
      <RouterLink v-if="isSuccess" class="btn primary" :to="{ name: 'downloads', params: { taskId } }">下載結果</RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from "vue";
import { RouterLink } from "vue-router";
import PageHeader from "@/components/PageHeader.vue";
import TaskProgressCard from "@/components/TaskProgressCard.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import { useTaskStore } from "@/stores/task";

const props = defineProps<{ taskId: string }>();
const taskId = props.taskId;

const task = useTaskStore();
const isSuccess = computed(() => String(task.status).toUpperCase() === "SUCCESS");

onMounted(() => {
  void task.startPolling(taskId);
});

onBeforeUnmount(() => {
  task.stopPolling();
});
</script>

<style scoped>
.actions {
  margin-top: 14px;
}
</style>
