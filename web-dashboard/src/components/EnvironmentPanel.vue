<script setup lang="ts">
defineProps<{
  targets: Array<{
    name: string;
    url: string;
  }>;
}>();
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">runtime</p>
        <h2>连接目标</h2>
      </div>
      <span class="pill">local</span>
    </div>

    <div class="target-list">
      <div v-for="target in targets" :key="target.name" class="target-row">
        <strong>{{ target.name }}</strong>
        <span>{{ target.url }}</span>
      </div>
    </div>
  </section>
</template>
