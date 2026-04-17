<template>
  <div class="row">
    <div class="col">
      <PageHeader
        title="Upload"
        subtitle="Upload a video and create a processing task."
      />

      <ErrorAlert v-if="task.error" :error="task.error" />
      <UploadForm :submitting="submitting" @submit="handleSubmit" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import PageHeader from "@/components/PageHeader.vue";
import UploadForm from "@/components/UploadForm.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import { useTaskStore } from "@/stores/task";
import type { APIError } from "@/types/api";

const router = useRouter();
const task = useTaskStore();
const submitting = ref(false);

async function handleSubmit(fd: FormData) {
  submitting.value = true;
  task.error = null;

  try {
    const res = await task.createTask(fd);
    await router.push({ name: "task", params: { taskId: res.task_id } });
  } catch (error) {
    task.error = error as APIError;
  } finally {
    submitting.value = false;
  }
}
</script>