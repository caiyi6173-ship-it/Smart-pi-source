<script setup lang="ts">
import AgentConsolePanel from "../components/AgentConsolePanel.vue";
import EventLogPanel from "../components/EventLogPanel.vue";
import ServiceHealthPanel from "../components/ServiceHealthPanel.vue";
import { useSystemStore } from "../stores/system";

const system = useSystemStore();
</script>

<template>
  <section class="page-grid two-col">
    <AgentConsolePanel @log="system.pushLog" />
    <div class="right-stack">
      <ServiceHealthPanel :services="system.services" @refresh="system.refreshStatus" />
      <EventLogPanel :logs="system.logs" />
    </div>
  </section>
</template>
