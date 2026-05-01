<template>
  <div>
    <PageHeader :title="$t('navbar.tasks')" subtitle="Last 20 tasks recorded by the backend." />

    <ErrorAlert v-if="error" :error="error" />
    <LoadingBlock v-if="loading" :title="$t('common.loading')" description="Fetching recent task history." />

    <EmptyState
      v-else-if="!error && tasks.length === 0"
      title="No recent tasks"
      description="No tasks have been recorded yet. Upload a video to create a task."
    />

    <div v-else class="card">
      <div class="card-inner">
        <!-- Filters -->
        <div class="filters">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search by Task ID or filename..."
            class="search-input"
          />
          <select v-model="statusFilter" class="status-filter">
            <option value="">{{ $t('task.status') }}</option>
            <option value="PENDING">PENDING</option>
            <option value="PROCESSING">PROCESSING</option>
            <option value="SUCCESS">SUCCESS</option>
            <option value="FAILURE">FAILURE</option>
            <option value="CANCELED">CANCELED</option>
          </select>
        </div>

        <table class="table">
          <thead>
            <tr>
              <th>Task ID</th>
              <th>Filename</th>
              <th>{{ $t('task.status') }}</th>
              <th>Created</th>
              <th>Duration</th>
              <th>Links</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in filteredTasks" :key="t.task_id">
              <td class="mono task-id">{{ t.task_id }}</td>
              <td class="mono filename">{{ t.filename || "-" }}</td>
              <td><StatusBadge :status="t.status" /></td>
              <td class="mono">{{ formatTs(t.created_at) }}</td>
              <td class="mono">{{ formatDuration(t.duration_seconds) }}</td>
              <td>
                <RouterLink class="btn small" :to="{ name: 'task', params: { taskId: t.task_id } }">{{ $t('task.status') }}</RouterLink>
                <RouterLink class="btn small" :to="{ name: 'subtitles', params: { taskId: t.task_id } }">{{ $t('editor.title') }}</RouterLink>
                <RouterLink class="btn small" :to="{ name: 'downloads', params: { taskId: t.task_id } }">{{ $t('editor.download') }}</RouterLink>
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
import { computed, onMounted, ref } from "vue";
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
const searchQuery = ref("");
const statusFilter = ref("");

function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "-";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs.toString().padStart(2, "0")}s`;
}

const filteredTasks = computed(() => {
  const query = searchQuery.value.toLowerCase().trim();
  const status = statusFilter.value.toUpperCase();

  return tasks.value.filter((t) => {
    // Status filter
    if (status && String(t.status).toUpperCase() !== status) {
      return false;
    }
    // Search filter (task_id or filename)
    if (query) {
      const taskIdMatch = t.task_id.toLowerCase().includes(query);
      const filenameMatch = (t.filename || "").toLowerCase().includes(query);
      if (!taskIdMatch && !filenameMatch) {
        return false;
      }
    }
    return true;
  });
});

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
.filters {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.search-input {
  flex: 1;
  min-width: 200px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.05);
  color: #fff;
  font-size: 14px;
}
.search-input::placeholder {
  color: rgba(255, 255, 255, 0.5);
}
.status-filter {
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.05);
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}
.task-id {
  font-size: 11px;
  opacity: 0.7;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.filename {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

