<script setup lang="ts">
import { storeToRefs } from "pinia";
import DeviceControlPanel from "../components/DeviceControlPanel.vue";
import EventLogPanel from "../components/EventLogPanel.vue";
import ServiceHealthPanel from "../components/ServiceHealthPanel.vue";
import VoicePanel from "../components/VoicePanel.vue";
import { useSystemStore } from "../stores/system";

const system = useSystemStore();
const { edge, logs, services, voice } = storeToRefs(system);
</script>

<template>
  <section class="page-grid two-col">
    <div class="left-stack">
      <DeviceControlPanel :edge="edge" @log="system.pushLog" />
      <VoicePanel :voice="voice" @log="system.pushLog" />
    </div>
    <div class="right-stack">
      <ServiceHealthPanel :services="services" @refresh="system.refreshStatus" />
      <EventLogPanel :logs="logs" />
    </div>
  </section>
</template>
