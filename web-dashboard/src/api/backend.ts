import { requestJson } from "./http";
import type { AgentResponse, RagResponse, ServiceHealth, VoiceStatus } from "../types";

export interface AuditLogRecord {
  id: number;
  event_type: string;
  actor: string;
  summary: string;
  payload: Record<string, unknown>;
  success: boolean;
  created_at: string;
}

async function safeWrite<T>(operation: () => Promise<T>): Promise<T | null> {
  try {
    return await operation();
  } catch {
    return null;
  }
}

export function listAuditLogs(limit = 20) {
  return requestJson<AuditLogRecord[]>(`/api/backend/api/v1/audit-logs?limit=${limit}`);
}

export function writeAuditLog(item: {
  event_type: string;
  actor?: string;
  summary: string;
  payload?: Record<string, unknown>;
  success?: boolean;
}) {
  return safeWrite(() =>
    requestJson<AuditLogRecord>("/api/backend/api/v1/audit-logs", {
      method: "POST",
      body: JSON.stringify({
        actor: "web-dashboard",
        payload: {},
        success: true,
        ...item
      })
    })
  );
}

export function writeRagMessage(question: string, result: RagResponse) {
  return safeWrite(() =>
    requestJson<Record<string, unknown>>("/api/backend/api/v1/rag/messages", {
      method: "POST",
      body: JSON.stringify({
        session_id: "web-dashboard",
        question,
        answer: result.answer,
        citations: result.citations ?? [],
        no_answer: Boolean(result.no_answer),
        evidence_status: result.evidence_status ?? "unknown",
        latency_ms: result.latency_ms ?? 0
      })
    })
  );
}

export function writeAgentRun(message: string, result: AgentResponse) {
  return safeWrite(() =>
    requestJson<Record<string, unknown>>("/api/backend/api/v1/agent/runs", {
      method: "POST",
      body: JSON.stringify({
        session_id: "web-dashboard",
        message,
        answer: result.answer,
        intent: result.intent,
        risk_level: result.risk_level,
        refused: result.refused,
        actions: result.actions ?? [],
        citations: result.citations ?? []
      })
    })
  );
}

export function writeDeviceAction(input: {
  action: string;
  path: string;
  parameters?: Record<string, unknown>;
  result?: Record<string, unknown>;
}) {
  return safeWrite(() =>
    requestJson<Record<string, unknown>>("/api/backend/api/v1/device-actions", {
      method: "POST",
      body: JSON.stringify({
        action: input.action,
        method: "POST",
        path: input.path,
        parameters: input.parameters ?? {},
        dry_run: Boolean(input.result?.dryRun ?? input.result?.dry_run ?? true),
        executed: Boolean(input.result?.executed ?? false),
        requires_confirmation: true,
        result: String(input.result?.message ?? input.result?.status ?? "")
      })
    })
  );
}

export function writeVoiceCommand(text: string, result: VoiceStatus) {
  return writeAuditLog({
    event_type: "voice_command",
    summary: text,
    payload: {
      reply: result.reply ?? result.lastReply ?? "",
      status: result.status ?? "unknown"
    },
    success: !result.lastError
  });
}

export function writeServiceSnapshots(services: ServiceHealth[]) {
  return Promise.all(
    services.map((service) =>
      safeWrite(() =>
        requestJson<Record<string, unknown>>("/api/backend/api/v1/service-snapshots", {
          method: "POST",
          body: JSON.stringify({
            service_name: service.name,
            state: service.state,
            detail: service.detail,
            latency_ms: service.latencyMs ?? null,
            payload: {
              updatedAt: service.updatedAt,
              mock: service.mock ?? false
            }
          })
        })
      )
    )
  );
}
