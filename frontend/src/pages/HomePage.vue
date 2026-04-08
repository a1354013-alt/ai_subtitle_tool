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
import { useRouter } from "vue-router";
import { ref } from "vue";
import PageHeader from "@/components/PageHeader.vue";
import UploadForm from "@/components/UploadForm.vue";
import ErrorAlert from "@/components/ErrorAlert.vue";
import { useTaskStore } from "@/stores/task";

const router = useRouter();
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
