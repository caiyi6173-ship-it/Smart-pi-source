export type ServiceState = "ok" | "degraded" | "down" | "unknown";

export interface ServiceHealth {
  name: string;
  state: ServiceState;
  detail: string;
  latencyMs?: number;
  updatedAt?: string;
  mock?: boolean;
}

export interface Citation {
  title?: string;
  source_id?: string;
  document_id?: string;
  chunk_id?: string;
  source_type?: string;
  score?: number | null;
  excerpt?: string | null;
}

export interface RagResponse {
  answer: string;
  citations: Citation[];
  rewritten_queries?: string[];
  retrieval_strategy?: string;
  rerank_provider?: string;
  no_answer?: boolean;
  evidence_status?: string;
  evidence_count?: number;
  model?: string;
  latency_ms?: number;
}

export interface AgentAction {
  action: string;
  parameters: Record<string, unknown>;
  method?: string;
  path?: string;
  action_marker?: string;
  requires_confirmation?: boolean;
  executed?: boolean;
  dry_run?: boolean;
  result?: string;
}

export interface AgentResponse {
  answer: string;
  citations: Citation[];
  actions: AgentAction[];
  risk_level: string;
  intent: string;
  refused: boolean;
}

export interface TelemetrySnapshot {
  running?: boolean;
  skinTemperatureC?: number | null;
  heartRate?: number | null;
  spo2?: number | null;
  sensorStatus?: Record<string, unknown>;
  lastError?: string | null;
  capturedAt?: string | null;
}

export interface VoiceStatus {
  status?: string;
  wakeListenEnabled?: boolean;
  lastUserText?: string;
  lastReply?: string;
  lastError?: string | null;
  updatedAt?: string;
  [key: string]: unknown;
}

export interface EdgeStatus {
  status?: string;
  cameraRunning?: boolean;
  sensorsRunning?: boolean;
  voiceStatus?: unknown;
  stream?: unknown;
  telemetry?: unknown;
  [key: string]: unknown;
}
