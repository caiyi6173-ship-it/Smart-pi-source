<script setup lang="ts">
import { ref } from "vue";

const emit = defineEmits<{
  log: [message: string];
}>();

const reloadKey = ref(Date.now());
const streamFailed = ref(false);

function reloadStream() {
  reloadKey.value = Date.now();
  streamFailed.value = false;
  emit("log", "刷新视频流");
}
</script>

<template>
  <section class="panel video-panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">mjpeg stream</p>
        <h2>实时舌象视频</h2>
      </div>
      <button class="icon-button" type="button" title="刷新视频流" @click="reloadStream">↻</button>
    </div>

    <div class="stream-frame">
      <img
        v-if="!streamFailed"
        :src="`/stream/mjpeg?ts=${reloadKey}`"
        alt="smartpi live stream"
        @error="streamFailed = true"
      />
      <div v-else class="mock-stream">
        <div class="scan-line"></div>
        <div class="tongue-shape"></div>
        <p>Mock 视频流</p>
        <span>摄像头服务未连接，当前显示演示占位</span>
      </div>
    </div>

    <div class="inline-actions">
      <a class="ghost-button" href="/stream/snapshot" target="_blank" rel="noreferrer">查看快照</a>
      <span>源：8081 /stream</span>
    </div>
  </section>
</template>
