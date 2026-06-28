<script setup lang="ts">
import RagChatPanel from "../components/RagChatPanel.vue";
import ServiceHealthPanel from "../components/ServiceHealthPanel.vue";
import { useSystemStore } from "../stores/system";

const system = useSystemStore();
</script>

<template>
  <section class="page-grid two-col">
    <RagChatPanel @log="system.pushLog" />
    <ServiceHealthPanel :services="system.services" @refresh="system.refreshStatus" />
  </section>
</template>
