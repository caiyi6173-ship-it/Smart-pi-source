<script setup lang="ts">
import { ref } from "vue";
import { writeRagMessage } from "../api/backend";
import { queryRag } from "../api/smartpi";
import type { RagResponse } from "../types";

const emit = defineEmits<{
  log: [message: string];
}>();

const question = ref("舌苔黄腻说明什么？");
const loading = ref(false);
const error = ref("");
const result = ref<RagResponse | null>(null);

async function submit() {
  if (!question.value.trim()) return;
  loading.value = true;
  error.value = "";
  try {
    const submittedQuestion = question.value.trim();
    result.value = await queryRag(submittedQuestion);
    const saved = await writeRagMessage(submittedQuestion, result.value);
    emit("log", `RAG 问答完成：${result.value.latency_ms ?? "-"} ms`);
    emit("log", saved ? "RAG 问答已写入 SQLite" : "RAG 问答未写入 SQLite：web-backend 不可用");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "RAG 请求失败";
    emit("log", `RAG 请求失败：${error.value}`);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <section class="panel tall-panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">rag</p>
        <h2>知识库问答</h2>
      </div>
      <span class="pill">{{ result?.retrieval_strategy ?? "hybrid" }}</span>
    </div>

    <form class="composer" @submit.prevent="submit">
      <textarea v-model="question" rows="3" placeholder="输入中医知识问题"></textarea>
      <button class="primary-button" type="submit" :disabled="loading">
        {{ loading ? "检索中" : "发送" }}
      </button>
    </form>

    <p v-if="error" class="error-text">{{ error }}</p>

    <article v-if="result" class="answer-card">
      <div class="answer-meta">
        <span>{{ result.model ?? "model" }}</span>
        <span>{{ result.latency_ms ?? "-" }} ms</span>
        <span>{{ result.evidence_status }}</span>
      </div>
      <p>{{ result.answer }}</p>
      <div v-if="result.citations.length" class="citation-list">
        <strong>引用</strong>
        <span v-for="citation in result.citations" :key="citation.chunk_id || citation.title">
          {{ citation.title || citation.source_id || "未知来源" }}
        </span>
      </div>
    </article>
  </section>
</template>
