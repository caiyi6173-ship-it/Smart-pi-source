<script setup lang="ts">
import { ref } from "vue";
import { writeDeviceAction } from "../api/backend";
import { postEdgeControl } from "../api/smartpi";
import type { EdgeStatus } from "../types";

defineProps<{
  edge: EdgeStatus;
}>();

const emit = defineEmits<{
  log: [message: string];
}>();

const busyAction = ref("");

const actions = [
  { label: "启动摄像头", path: "/control/camera/start", payload: { profile: "low-latency" }, confirm: "确认请求启动摄像头？" },
  { label: "停止摄像头", path: "/control/camera/stop", payload: {}, confirm: "确认请求停止摄像头？" },
  { label: "启动传感器", path: "/control/sensors/start", payload: {}, confirm: "确认请求启动传感器？" },
  { label: "停止传感器", path: "/control/sensors/stop", payload: {}, confirm: "确认请求停止传感器？" },
  { label: "手动唤醒", path: "/control/voice/manual-wake", payload: { speakReply: false }, confirm: "确认触发语音助手手动唤醒？" },
  { label: "触发分析", path: "/analysis/trigger", payload: {}, confirm: "确认触发一次设备分析？" }
];

async function runAction(action: (typeof actions)[number]) {
  if (!window.confirm(action.confirm)) {
    return;
  }
  busyAction.value = action.path;
  try {
    const result = await postEdgeControl(action.path, action.payload);
    const saved = await writeDeviceAction({
      action: action.label,
      path: action.path,
      parameters: action.payload,
      result
    });
    emit("log", `${action.label}：${String(result.status ?? result.message ?? "完成")}`);
    emit("log", saved ? "设备动作已写入 SQLite" : "设备动作未写入 SQLite：web-backend 不可用");
  } catch (error) {
    const message = error instanceof Error ? error.message : "请求失败";
    emit("log", `${action.label}失败：${message}`);
  } finally {
    busyAction.value = "";
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">device</p>
        <h2>设备控制</h2>
      </div>
      <span class="pill">{{ edge.status ?? "edge" }}</span>
    </div>

    <div class="control-grid">
      <button
        v-for="action in actions"
        :key="action.path"
        class="control-button"
        type="button"
        :disabled="busyAction === action.path"
        @click="runAction(action)"
      >
        {{ busyAction === action.path ? "请求中" : action.label }}
      </button>
    </div>
  </section>
</template>
