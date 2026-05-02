<template>
  <div class="language-switcher">
    <select v-model="currentLang" @change="changeLanguage" class="lang-select">
      <option value="zh-TW">繁體中文</option>
      <option value="en">English</option>
      <option value="ja">日本語</option>
    </select>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

const { locale } = useI18n();
const currentLang = ref(locale.value);

const changeLanguage = () => {
  locale.value = currentLang.value;
  localStorage.setItem('lang', currentLang.value);
};
</script>

<style scoped>
.language-switcher {
  display: flex;
  align-items: center;
}

.lang-select {
  padding: 0.5rem 0.75rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  background-color: white;
  cursor: pointer;
  font-size: 0.875rem;
  transition: border-color 0.2s;
}

.lang-select:hover {
  border-color: #999;
}

.lang-select:focus {
  outline: none;
  border-color: #0066cc;
  box-shadow: 0 0 0 2px rgba(0, 102, 204, 0.1);
}
</style>
