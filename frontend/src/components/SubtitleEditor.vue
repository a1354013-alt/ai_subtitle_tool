<template>
  <div class="card">
    <div class="card-inner">
      <div class="row" style="align-items: center; justify-content: space-between">
        <div>
          <div class="label">{{ $t('editor.title') }}</div>
          <div class="help">{{ $t('editor.panelHelp') }}</div>
        </div>
        <div class="row" style="align-items: center">
          <span v-if="savedHint" class="pill">{{ $t('editor.savedAt') }}: {{ savedHint }}</span>
          <button class="btn primary" :disabled="saving || !dirty" @click="$emit('save')">
            {{ saving ? $t('common.loading') : $t('editor.save') }}
          </button>
        </div>
      </div>

      <div style="margin-top: 12px">
        <textarea class="textarea" :value="modelValue" @input="onInput" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  modelValue: string;
  dirty: boolean;
  saving: boolean;
  lastSavedAt?: number | null;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: string): void;
  (e: "save"): void;
}>();

function onInput(e: Event) {
  const ta = e.target as HTMLTextAreaElement;
  emit("update:modelValue", ta.value);
}

const savedHint = computed(() => {
  if (!props.lastSavedAt) return "";
  const d = new Date(props.lastSavedAt);
  return d.toLocaleString();
});
</script>
