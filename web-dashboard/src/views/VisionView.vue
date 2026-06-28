<script setup lang="ts">
import { storeToRefs } from "pinia";
import DeviceControlPanel from "../components/DeviceControlPanel.vue";
import TelemetryPanel from "../components/TelemetryPanel.vue";
import VideoPanel from "../components/VideoPanel.vue";
import { useSystemStore } from "../stores/system";

const system = useSystemStore();
const { edge, telemetry } = storeToRefs(system);
</script>

<template>
  <section class="page-grid two-col">
    <VideoPanel @log="system.pushLog" />
    <div class="right-stack">
      <TelemetryPanel :telemetry="telemetry" />
      <DeviceControlPanel :edge="edge" @log="system.pushLog" />
    </div>
  </section>
</template>
