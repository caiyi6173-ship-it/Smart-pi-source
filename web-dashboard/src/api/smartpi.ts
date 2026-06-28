import { requestJson } from "./http";
import {
  mockAgentHealth,
  mockChatAgent,
  mockEdgeControl,
  mockEdgeStatus,
  mockQueryRag,
  mockRagHealth,
  mockTelemetry,
  mockVoiceCommand,
  mockVoiceHealth
} from "./mock";
import type { AgentResponse, EdgeStatus, RagResponse, TelemetrySnapshot, VoiceStatus } from "../types";

type MockMode = "auto" | "on" | "off";

const mockMode = ((import.meta.env.VITE_MOCK_API as string | undefined) || "auto") as MockMode;

async function withMockFallback<T>(realCall: () => Promise<T>, mockCall: () => Promise<T>): Promise<T> {
  if (mockMode === "on") {
    return mockCall();
  }
  if (mockMode === "off") {
    return realCall();
  }
  try {
    return await realCall();
  } catch {
    return mockCall();
  }
}

export function getMockMode() {
  return mockMode;
}

export function getRagHealth() {
  return withMockFallback(() => requestJson<Record<string, unknown>>("/api/rag/health"), mockRagHealth);
}

export function getAgentHealth() {
  return withMockFallback(() => requestJson<Record<string, unknown>>("/api/agent/health"), mockAgentHealth);
}

export function getVoiceHealth() {
  return withMockFallback(() => requestJson<VoiceStatus>("/api/voice/health"), mockVoiceHealth);
}

export function getEdgeStatus() {
  return withMockFallback(() => requestJson<EdgeStatus>("/api/edge/status"), mockEdgeStatus);
}

export function getTelemetry() {
  return withMockFallback(() => requestJson<TelemetrySnapshot>("/api/sensor/telemetry/latest"), mockTelemetry);
}

export function queryRag(question: string) {
  return withMockFallback(
    () =>
      requestJson<RagResponse>("/api/rag/api/v1/query", {
        method: "POST",
        body: JSON.stringify({
          question,
          top_k: 8,
          include_chunks: false
        })
      }),
    () => mockQueryRag(question)
  );
}

export function chatAgent(message: string) {
  return withMockFallback(
    () =>
      requestJson<AgentResponse>("/api/agent/api/v1/agent/chat", {
        method: "POST",
        body: JSON.stringify({
          session_id: "web-dashboard",
          message,
          input_type: "text",
          options: {
            include_trace: true,
            include_citations: true
          }
        })
      }),
    () => mockChatAgent(message)
  );
}

export function sendVoiceCommand(text: string, speakReply = false) {
  return withMockFallback(
    () =>
      requestJson<VoiceStatus>("/api/voice/command", {
        method: "POST",
        body: JSON.stringify({ text, speakReply })
      }),
    () => mockVoiceCommand(text)
  );
}

export function postEdgeControl(path: string, payload: Record<string, unknown> = {}) {
  return withMockFallback(
    () =>
      requestJson<Record<string, unknown>>(`/api/edge${path}`, {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    () => mockEdgeControl(path)
  );
}
