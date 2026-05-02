<template>
  <div>
    <header class="shell">
      <div class="container shell-inner">
        <div class="brand">
          <div class="logo">AI</div>
          <div>
            <div class="title">{{ $t('navbar.title') }}</div>
            <div class="subtitle">{{ $t('navbar.subtitle') }}</div>
          </div>
        </div>

        <nav class="nav">
          <RouterLink class="nav-link" to="/">{{ $t('navbar.home') }}</RouterLink>
          <RouterLink class="nav-link" to="/tasks/recent">{{ $t('navbar.tasks') }}</RouterLink>
          <LanguageSwitcher />
        </nav>
      </div>
    </header>

    <main class="container">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { RouterLink } from "vue-router";
import LanguageSwitcher from "./LanguageSwitcher.vue";
</script>

<style scoped>
.shell {
  position: sticky;
  top: 0;
  z-index: 20;
  backdrop-filter: blur(14px);
  background: rgba(5, 8, 22, 0.55);
  border-bottom: 1px solid rgba(255, 255, 255, 0.10);
}
.shell-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-top: 14px;
  padding-bottom: 14px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.logo {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  border: 1px solid rgba(110, 168, 254, 0.45);
  background: rgba(110, 168, 254, 0.12);
  display: grid;
  place-items: center;
  font-weight: 800;
}
.title {
  font-weight: 700;
  letter-spacing: 0.2px;
}
.subtitle {
  font-size: 12px;
  color: var(--color-muted);
  margin-top: 2px;
}
.nav {
  display: flex;
  gap: 10px;
  align-items: center;
}
.nav-link {
  padding: 8px 10px;
  border: 1px solid rgba(255, 255, 255, 0.10);
  background: rgba(255, 255, 255, 0.04);
  border-radius: 12px;
  color: var(--color-muted);
}
.nav-link.router-link-active {
  color: var(--color-text);
  border-color: rgba(110, 168, 254, 0.45);
  background: rgba(110, 168, 254, 0.10);
}
</style>
