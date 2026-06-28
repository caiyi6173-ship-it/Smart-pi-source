<script setup lang="ts">
import { ref } from "vue";
import { writeAgentRun } from "../api/backend";
import { chatAgent } from "../api/smartpi";
import type { AgentResponse } from "../types";

const emit = defineEmits<{
  log: [message: string];
}>();

const message = ref("打开摄像头识别");
const loading = ref(false);
const error = ref("");
const result = ref<AgentResponse | null>(null);

async function submit() {
  if (!message.value.trim()) return;
  loading.value = true;
  error.value = "";
  try {
    const submittedMessage = message.value.trim();
    result.value = await chatAgent(submittedMessage);
    const saved = await writeAgentRun(submittedMessage, result.value);
    emit("log", `Agent 完成：${result.value.intent}`);
    emit("log", saved ? "Agent 运行已写入 SQLite" : "Agent 运行未写入 SQLite：web-backend 不可用");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Agent 请求失败";
    emit("log", `Agent 请求失败：${error.value}`);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <section class="panel tall-panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">agent</p>
        <h2>智能体编排</h2>
      </div>
      <span class="pill">{{ result?.intent ?? "idle" }}</span>
    </div>

    <form class="composer" @submit.prevent="submit">
      <textarea v-model="message" rows="3" placeholder="输入设备控制或知识问题"></textarea>
      <button class="primary-button" type="submit" :disabled="loading">
        {{ loading ? "处理中" : "发送" }}
      </button>
    </form>

    <p v-if="error" class="error-text">{{ error }}</p>

    <article v-if="result" class="answer-card">
      <div class="answer-meta">
        <span>risk: {{ result.risk_level }}</span>
        <span>refused: {{ result.refused ? "yes" : "no" }}</span>
      </div>
      <p>{{ result.answer }}</p>
      <div v-if="result.actions.length" class="action-list">
        <strong>动作</strong>
        <div v-for="action in result.actions" :key="action.action + action.path" class="action-row">
          <span>{{ action.action }}</span>
          <small>{{ action.dry_run ? "dry-run" : "execute" }}</small>
        </div>
      </div>
    </article>
  </section>
</template>
