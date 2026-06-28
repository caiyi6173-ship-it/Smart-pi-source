import { defineStore } from "pinia";
import { ref } from "vue";
import { writeServiceSnapshots } from "../api/backend";
import { getAgentHealth, getEdgeStatus, getMockMode, getRagHealth, getTelemetry, getVoiceHealth } from "../api/smartpi";
import type { EdgeStatus, ServiceHealth, TelemetrySnapshot, VoiceStatus } from "../types";

export const useSystemStore = defineStore("system", () => {
  const services = ref<ServiceHealth[]>([
    { name: "RAG", state: "unknown", detail: "等待检测" },
    { name: "Agent", state: "unknown", detail: "等待检测" },
    { name: "Voice", state: "unknown", detail: "等待检测" },
    { name: "Edge", state: "unknown", detail: "等待检测" },
    { name: "Sensor", state: "unknown", detail: "等待检测" }
  ]);
  const telemetry = ref<TelemetrySnapshot>({});
  const voice = ref<VoiceStatus>({});
  const edge = ref<EdgeStatus>({});
  const logs = ref<string[]>([]);
  const mockMode = getMockMode();
  const targets = [
    { name: "RAG", url: import.meta.env.VITE_RAG_TARGET || "http://127.0.0.1:8095" },
    { name: "Agent", url: import.meta.env.VITE_AGENT_TARGET || "http://127.0.0.1:8096" },
    { name: "Voice", url: import.meta.env.VITE_VOICE_TARGET || "http://127.0.0.1:8093" },
    { name: "Edge", url: import.meta.env.VITE_EDGE_TARGET || "http://127.0.0.1:8092" },
    { name: "Sensor", url: import.meta.env.VITE_SENSOR_TARGET || "http://127.0.0.1:8091" },
    { name: "Stream", url: import.meta.env.VITE_STREAM_TARGET || "http://127.0.0.1:8081" }
  ];
  let timer: number | undefined;
  let lastSnapshotWriteAt = 0;

  function pushLog(message: string) {
    const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    logs.value = [`${time} ${message}`, ...logs.value].slice(0, 80);
  }

  async function probe(name: string, fn: () => Promise<unknown>, okField = "status") {
    const started = performance.now();
    try {
      const result = (await fn()) as Record<string, unknown>;
      const rawValue = result[okField] ?? result.status ?? "ok";
      const rawStatus = String(rawValue).toLowerCase();
      const state = rawValue === true || rawStatus === "ok" || rawStatus === "up" ? "ok" : "degraded";
      return {
        name,
        state,
        detail: result.mock ? `${rawStatus} · mock` : rawStatus,
        latencyMs: Math.round(performance.now() - started),
        updatedAt: new Date().toLocaleTimeString("zh-CN", { hour12: false }),
        mock: Boolean(result.mock)
      } satisfies ServiceHealth;
    } catch (error) {
      return {
        name,
        state: "down",
        detail: error instanceof Error ? error.message : "连接失败",
        latencyMs: Math.round(performance.now() - started),
        updatedAt: new Date().toLocaleTimeString("zh-CN", { hour12: false })
      } satisfies ServiceHealth;
    }
  }

  async function refreshStatus() {
    const [rag, agent, voiceHealth, edgeStatus, sensor] = await Promise.all([
      probe("RAG", getRagHealth),
      probe("Agent", getAgentHealth),
      probe("Voice", getVoiceHealth),
      probe("Edge", getEdgeStatus),
      probe("Sensor", getTelemetry, "running")
    ]);
    services.value = [rag, agent, voiceHealth, edgeStatus, sensor];
    if (Date.now() - lastSnapshotWriteAt > 30_000) {
      lastSnapshotWriteAt = Date.now();
      void writeServiceSnapshots(services.value).then((saved) => {
        if (saved.some(Boolean)) {
          pushLog("服务健康快照已写入 SQLite");
        }
      });
    }

    try {
      telemetry.value = await getTelemetry();
    } catch {
      telemetry.value = {};
    }

    try {
      voice.value = await getVoiceHealth();
    } catch {
      voice.value = {};
    }

    try {
      edge.value = await getEdgeStatus();
    } catch {
      edge.value = {};
    }
  }

  function startPolling() {
    if (timer) return;
    void refreshStatus();
    timer = window.setInterval(refreshStatus, 3000);
    pushLog("Web 控制台已启动，本地模式");
    if (mockMode !== "off") {
      pushLog(`Mock API 模式：${mockMode}`);
    }
  }

  function stopPolling() {
    if (!timer) return;
    window.clearInterval(timer);
    timer = undefined;
  }

  return {
    edge,
    logs,
    mockMode,
    services,
    targets,
    telemetry,
    voice,
    pushLog,
    refreshStatus,
    startPolling,
    stopPolling
  };
});
