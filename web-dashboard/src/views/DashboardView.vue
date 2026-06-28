<script setup lang="ts">
import { storeToRefs } from "pinia";
import AgentConsolePanel from "../components/AgentConsolePanel.vue";
import DeviceControlPanel from "../components/DeviceControlPanel.vue";
import EnvironmentPanel from "../components/EnvironmentPanel.vue";
import EventLogPanel from "../components/EventLogPanel.vue";
import RagChatPanel from "../components/RagChatPanel.vue";
import ServiceHealthPanel from "../components/ServiceHealthPanel.vue";
import TelemetryPanel from "../components/TelemetryPanel.vue";
import VideoPanel from "../components/VideoPanel.vue";
import VoicePanel from "../components/VoicePanel.vue";
import { useSystemStore } from "../stores/system";

const system = useSystemStore();
const { edge, logs, services, targets, telemetry, voice } = storeToRefs(system);
</script>

<template>
  <section class="grid">
    <aside class="left-stack">
      <VideoPanel @log="system.pushLog" />
      <DeviceControlPanel :edge="edge" @log="system.pushLog" />
    </aside>

    <section class="center-stack">
      <RagChatPanel @log="system.pushLog" />
      <AgentConsolePanel @log="system.pushLog" />
    </section>

    <aside class="right-stack">
      <EnvironmentPanel :targets="targets" />
      <ServiceHealthPanel :services="services" @refresh="system.refreshStatus" />
      <TelemetryPanel :telemetry="telemetry" />
      <VoicePanel :voice="voice" @log="system.pushLog" />
      <EventLogPanel :logs="logs" />
    </aside>
  </section>
</template>
