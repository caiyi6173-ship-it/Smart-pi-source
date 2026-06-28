<script setup lang="ts">
import { onMounted, ref } from "vue";
import { listAuditLogs, type AuditLogRecord } from "../api/backend";

const logs = ref<AuditLogRecord[]>([]);
const loading = ref(false);
const error = ref("");

async function refresh() {
  loading.value = true;
  error.value = "";
  try {
    logs.value = await listAuditLogs(20);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "读取 SQLite 记录失败";
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void refresh();
});
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">sqlite</p>
        <h2>最近审计记录</h2>
      </div>
      <button class="icon-button" type="button" title="刷新" @click="refresh">↻</button>
    </div>

    <p v-if="loading" class="muted">读取中...</p>
    <p v-else-if="error" class="error-text">{{ error }}</p>
    <div v-else class="audit-list">
      <article v-for="item in logs" :key="item.id" class="audit-row">
        <div>
          <strong>{{ item.event_type }}</strong>
          <span>{{ item.summary }}</span>
        </div>
        <small>{{ item.created_at }}</small>
      </article>
      <p v-if="!logs.length" class="muted">暂无 SQLite 审计记录</p>
    </div>
  </section>
</template>
