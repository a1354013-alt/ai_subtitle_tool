<template>
  <div class="row">
    <div class="col">
      <PageHeader
        :title="$t('upload.title')"
        subtitle="Upload a video and create a processing task."
      />

      <div class="tabs-container">
        <button 
          class="tab-btn" 
          :class="{ active: mode === 'single' }" 
          @click="mode = 'single'"
        >
          Single Video
        </button>
        <button 
          class="tab-btn" 
          :class="{ active: mode === 'batch' }" 
          @click="mode = 'batch'"
        >
          Batch Processing
        </button>
      </div>

      <ErrorAlert v-if="task.error" :error="task.error" />
      
      <div v-if="mode === 'single'">
        <UploadForm :submitting="submitting" @submit="handleSubmit" />
      </div>
      <div v-else>
        <BatchUploadPanel />
      </div>
    </div>
  </div>
</template>

<style scoped>
.tabs-container {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}
.tab-btn {
  padding: 10px 20px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-muted);
  cursor: pointer;
  transition: all 0.2s;
}
.tab-btn.active {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}
</style>

<script setup lang="ts">
import { useRouter } from "vue-router";
import { ref } from "vue";
import PageHeader from "@/components/PageHeader.vue";
import UploadForm from "@/components/UploadForm.vue";
import BatchUploadPanel from "@/components/BatchUploadPanel.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import { useTaskStore } from "@/stores/task";

const router = useRouter();
const mode = ref<"single" | "batch">("single");
const task = useTaskStore();
const submitting = ref(false);

async function handleSubmit(fd: FormData) {
  submitting.value = true;
  try {
    const res = await task.createTask(fd);
    await router.push({ name: "task", params: { taskId: res.task_id } });
  } finally {
    submitting.value = false;
  }
}
</script>
