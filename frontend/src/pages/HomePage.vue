<template>
  <div class="row">
    <div class="col">
      <PageHeader title="上傳影片" subtitle="使用 multipart/form-data 建立任務。建立後會導向任務狀態頁，並由前端輪詢進度。" />

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
  } catch {
    // 錯誤由 store 設定並由 ErrorAlert 顯示
  } finally {
    submitting.value = false;
  }
}
</script>
