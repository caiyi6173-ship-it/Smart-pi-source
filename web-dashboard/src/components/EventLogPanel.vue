<script setup lang="ts">
defineProps<{
  logs: string[];
}>();
</script>

<template>
  <section class="panel log-panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">events</p>
        <h2>事件日志</h2>
      </div>
    </div>

    <div class="log-list">
      <p v-for="log in logs" :key="log">{{ log }}</p>
      <p v-if="!logs.length" class="muted">暂无事件</p>
    </div>
  </section>
</template>
