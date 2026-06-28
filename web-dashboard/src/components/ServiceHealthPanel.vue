<script setup lang="ts">
import type { ServiceHealth } from "../types";

defineProps<{
  services: ServiceHealth[];
}>();

defineEmits<{
  refresh: [];
}>();
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">services</p>
        <h2>服务健康</h2>
      </div>
      <button class="icon-button" type="button" title="刷新" @click="$emit('refresh')">↻</button>
    </div>

    <div class="health-list">
      <article v-for="service in services" :key="service.name" class="health-row">
        <div>
          <strong>{{ service.name }}</strong>
          <span>{{ service.detail }}</span>
        </div>
        <div class="health-meta">
          <small v-if="service.mock" class="mock-chip">mock</small>
          <span :class="['status-dot', service.state]"></span>
          <small>{{ service.latencyMs ?? "-" }} ms</small>
        </div>
      </article>
    </div>
  </section>
</template>
