<script setup lang="ts">
import { ref } from "vue";
import { writeVoiceCommand } from "../api/backend";
import { sendVoiceCommand } from "../api/smartpi";
import type { VoiceStatus } from "../types";

defineProps<{
  voice: VoiceStatus;
}>();

const emit = defineEmits<{
  log: [message: string];
}>();

const text = ref("舌苔黄腻说明什么？");
const loading = ref(false);
const reply = ref("");

async function send() {
  if (!text.value.trim()) return;
  loading.value = true;
  try {
    const submittedText = text.value.trim();
    const result = await sendVoiceCommand(submittedText, false);
    reply.value = String(result.reply ?? result.lastReply ?? "已发送");
    const saved = await writeVoiceCommand(submittedText, result);
    emit("log", "语音助手文本命令完成");
    emit("log", saved ? "语音命令已写入 SQLite" : "语音命令未写入 SQLite：web-backend 不可用");
  } catch (error) {
    reply.value = error instanceof Error ? error.message : "语音命令失败";
    emit("log", `语音命令失败：${reply.value}`);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">voice</p>
        <h2>语音助手</h2>
      </div>
      <span class="pill">{{ voice.status ?? "unknown" }}</span>
    </div>

    <div class="mini-form">
      <input v-model="text" type="text" placeholder="文本命令" />
      <button class="primary-button" type="button" :disabled="loading" @click="send">
        {{ loading ? "发送中" : "发送" }}
      </button>
    </div>

    <p class="muted">唤醒监听：{{ voice.wakeListenEnabled ? "开启" : "未知或关闭" }}</p>
    <p v-if="reply" class="reply-text">{{ reply }}</p>
  </section>
</template>
