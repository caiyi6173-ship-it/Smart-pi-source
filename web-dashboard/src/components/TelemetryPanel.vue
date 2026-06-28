<script setup lang="ts">
import type { TelemetrySnapshot } from "../types";

defineProps<{
  telemetry: TelemetrySnapshot;
}>();
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">telemetry</p>
        <h2>传感器</h2>
      </div>
    </div>

    <div class="metric-grid">
      <div class="metric">
        <span>皮肤温度</span>
        <strong>{{ telemetry.skinTemperatureC ?? "--" }}</strong>
      </div>
      <div class="metric">
        <span>心率</span>
        <strong>{{ telemetry.heartRate ?? "--" }}</strong>
      </div>
      <div class="metric">
        <span>血氧</span>
        <strong>{{ telemetry.spo2 ?? "--" }}</strong>
      </div>
    </div>

    <p class="muted">运行：{{ telemetry.running === true ? "是" : telemetry.running === false ? "否" : "未知" }}</p>
    <p v-if="telemetry.lastError" class="error-text">{{ telemetry.lastError }}</p>
  </section>
</template>
