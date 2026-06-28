<script setup lang="ts">
import { storeToRefs } from "pinia";
import AuditLogPanel from "../components/AuditLogPanel.vue";
import EnvironmentPanel from "../components/EnvironmentPanel.vue";
import ServiceHealthPanel from "../components/ServiceHealthPanel.vue";
import { useSystemStore } from "../stores/system";

const system = useSystemStore();
const { services, targets } = storeToRefs(system);
</script>

<template>
  <section class="page-grid two-col">
    <div class="left-stack">
      <EnvironmentPanel :targets="targets" />
      <AuditLogPanel />
    </div>
    <ServiceHealthPanel :services="services" @refresh="system.refreshStatus" />
  </section>
</template>
