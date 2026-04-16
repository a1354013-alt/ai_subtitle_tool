<template>
  <div>
    <PageHeader title="Recent Tasks" subtitle="Last 20 tasks recorded by the backend." />

    <ErrorAlert v-if="error" :error="error" />
    <LoadingBlock v-if="loading" title="Loading tasks..." description="Fetching recent task history." />

    <EmptyState
      v-else-if="!error && tasks.length === 0"
      title="No recent tasks"
      description="No tasks have been recorded yet. Upload a video to create a task."
    />

    <div v-else class="card">
      <div class="card-inner">
        <table class="table">
          <thead>
            <tr>
              <th>Filename</th>
              <th>Status</th>
              <th>Created</th>
              <th>Links</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in tasks" :key="t.task_id">
              <td class="mono">{{ t.filename || t.task_id }}</td>
              <td><StatusBadge :status="t.status" /></td>
              <td class="mono">{{ formatTs(t.created_at) }}</td>
              <td>
                <RouterLink class="btn small" :to="{ name: 'task', params: { taskId: t.task_id } }">Status</RouterLink>
                <RouterLink class="btn small" :to="{ name: 'subtitles', params: { taskId: t.task_id } }">Subtitles</RouterLink>
                <RouterLink class="btn small" :to="{ name: 'downloads', params: { taskId: t.task_id } }">Downloads</RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="help" style="margin-top: 10px">
          Notes: filenames are recorded at upload time. If this backend was upgraded, older tasks may show only task id.
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import PageHeader from "@/components/PageHeader.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import EmptyState from "@/components/EmptyState.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import { getRecentTasks } from "@/api/tasks";
import type { APIError } from "@/types/api";
import type { RecentTask } from "@/types/task";

const loading = ref(false);
const error = ref<APIError | null>(null);
const tasks = ref<RecentTask[]>([]);

function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

onMounted(async () => {
  loading.value = true;
  error.value = null;
  try {
    tasks.value = await getRecentTasks();
  } catch (e) {
    error.value = e as APIError;
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.table {
  width: 100%;
  border-collapse: collapse;
}
.table th,
.table td {
  text-align: left;
  padding: 10px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  vertical-align: top;
}
.btn.small {
  padding: 6px 8px;
  font-size: 12px;
  margin-right: 6px;
}
</style>

