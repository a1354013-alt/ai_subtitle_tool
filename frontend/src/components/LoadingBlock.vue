<template>
  <div class="card">
    <div class="card-inner">
      <div class="row">
        <div class="spinner" />
        <div>
          <div class="t">{{ title }}</div>
          <div class="d">{{ description }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    description?: string;
  }>(),
  {
    title: "Loading...",
    description: "Please wait.",
  }
);
</script>

<style scoped>
.spinner {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: rgba(110, 168, 254, 0.9);
  animation: spin 0.9s linear infinite;
  margin-top: 2px;
}
.t {
  font-weight: 800;
}
.d {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
