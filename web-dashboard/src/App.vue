<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import { RouterLink, RouterView } from "vue-router";
import { useSystemStore } from "./stores/system";

const system = useSystemStore();
const navItems = [
  { label: "总览", to: "/dashboard" },
  { label: "视觉", to: "/vision" },
  { label: "RAG", to: "/rag" },
  { label: "Agent", to: "/agent" },
  { label: "设备", to: "/devices" },
  { label: "设置", to: "/settings" }
];

onMounted(() => {
  system.startPolling();
});

onUnmounted(() => {
  system.stopPolling();
});
</script>

<template>
  <main class="shell app-shell">
    <aside class="sidebar">
      <div class="brand">
        <p class="eyebrow">SmartPI</p>
        <h1>中医智能设备控制台</h1>
      </div>

      <nav class="side-nav">
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to">
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="sidebar-foot">
        <span>电脑本地</span>
        <strong>127.0.0.1</strong>
        <small>Mock API: {{ system.mockMode }}</small>
      </div>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">local development</p>
          <h2>运行控制台</h2>
        </div>
        <button class="ghost-button" type="button" @click="system.refreshStatus">刷新状态</button>
      </header>

      <RouterView />
    </section>
  </main>
</template>
