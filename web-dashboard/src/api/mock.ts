import type { AgentResponse, EdgeStatus, RagResponse, TelemetrySnapshot, VoiceStatus } from "../types";

const startedAt = Date.now();

function delay(ms = 240) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function nowIso() {
  return new Date().toISOString();
}

function wave(base: number, range: number, speed = 9000) {
  return Number((base + Math.sin(Date.now() / speed) * range).toFixed(1));
}

export async function mockRagHealth() {
  await delay(90);
  return {
    status: "ok",
    vector_backend: "mock-chroma",
    vector_store: true,
    embedding_configured: true,
    llm_configured: true,
    collection: "smartpi_demo",
    mock: true
  };
}

export async function mockAgentHealth() {
  await delay(80);
  return {
    status: "ok",
    service: "smartpi-agent-orchestrator",
    version: "0.1.0-demo",
    rag_base_url: "mock://rag",
    openclaw_configured: true,
    mock: true
  };
}

export async function mockVoiceHealth(): Promise<VoiceStatus> {
  await delay(100);
  return {
    status: "idle",
    wakeListenEnabled: true,
    lastUserText: "舌苔黄腻说明什么？",
    lastReply: "演示模式：语音助手在线，等待文本或唤醒指令。",
    lastError: null,
    updatedAt: nowIso(),
    mock: true
  };
}

export async function mockEdgeStatus(): Promise<EdgeStatus> {
  await delay(110);
  return {
    status: "UP",
    cameraRunning: true,
    sensorsRunning: true,
    stream: {
      running: true,
      url: "/stream/mock"
    },
    telemetry: {
      skinTemperatureC: wave(35.8, 0.4),
      heartRate: Math.round(wave(76, 6, 7000)),
      spo2: Math.round(wave(98, 1.2, 11000))
    },
    uptimeSeconds: Math.round((Date.now() - startedAt) / 1000),
    mock: true
  };
}

export async function mockTelemetry(): Promise<TelemetrySnapshot> {
  await delay(120);
  return {
    running: true,
    skinTemperatureC: wave(35.8, 0.4),
    heartRate: Math.round(wave(76, 6, 7000)),
    spo2: Math.round(wave(98, 1.2, 11000)),
    sensorStatus: {
      temperature: "ok",
      pulseox: "ok"
    },
    lastError: null,
    capturedAt: nowIso()
  };
}

export async function mockQueryRag(question: string): Promise<RagResponse> {
  await delay(520);
  const normalized = question.trim();
  return {
    answer:
      `演示模式回答：关于“${normalized || "舌象问题"}”，知识库会先进行 query rewrite，然后用 BM25 + 向量混合检索召回现代科普与古籍片段，再经过 reranker 重排。` +
      "\n\n如果问题涉及具体诊断、儿童、孕产、急症或用药冲突，系统应提示线下就医。仅供中医知识参考，不能替代医生诊断。",
    citations: [
      {
        title: "中医药基础科普演示资料",
        source_id: "mock-modern-basics",
        document_id: "mock_doc_001",
        chunk_id: "mock_chunk_001",
        source_type: "modern_basics",
        score: 0.92,
        excerpt: "舌苔黄腻常用于中医知识解释场景，需结合症状、体质和专业诊察。"
      },
      {
        title: "古籍知识演示片段",
        source_id: "mock-classic-text",
        document_id: "mock_doc_002",
        chunk_id: "mock_chunk_014",
        source_type: "classic_text",
        score: 0.81,
        excerpt: "古籍内容用于知识解释和出处参考，不应直接替代现代临床判断。"
      }
    ],
    rewritten_queries: [normalized, `${normalized} 中医知识解释`, `${normalized} 安全边界`],
    retrieval_strategy: "mock-hybrid-bm25-vector",
    rerank_provider: "mock-cross-encoder",
    no_answer: false,
    evidence_status: "supported",
    evidence_count: 2,
    model: "mock-qwen-compatible",
    latency_ms: 520
  };
}

export async function mockChatAgent(message: string): Promise<AgentResponse> {
  await delay(430);
  const isDevice = /摄像头|传感器|打开|关闭|识别|唤醒|分析/.test(message);
  return {
    answer: isDevice
      ? "演示模式：已识别为设备控制意图，当前只生成 dry-run 动作，不执行真实硬件控制。"
      : "演示模式：已通过 Supervisor Agent 路由到 RAG / Safety / Response Agent，并生成安全回答。",
    citations: isDevice
      ? []
      : [
          {
            title: "中医药基础科普演示资料",
            source_id: "mock-modern-basics",
            document_id: "mock_doc_001",
            chunk_id: "mock_chunk_001",
            source_type: "modern_basics",
            score: 0.9
          }
        ],
    actions: isDevice
      ? [
          {
            action: "camera.start",
            parameters: { profile: "low-latency" },
            method: "POST",
            path: "/control/camera/start",
            action_marker: "[[SMARTPI_ACTION:camera.start]]",
            requires_confirmation: true,
            executed: false,
            dry_run: true,
            result: "演示模式未执行真实硬件动作"
          }
        ]
      : [],
    risk_level: "low",
    intent: isDevice ? "device_control" : "tcm_knowledge",
    refused: false
  };
}

export async function mockVoiceCommand(text: string): Promise<VoiceStatus> {
  await delay(360);
  return {
    status: "idle",
    wakeListenEnabled: true,
    lastUserText: text,
    lastReply: `演示模式：语音助手已收到“${text}”，未播放真实 TTS。`,
    reply: `演示模式：语音助手已收到“${text}”，未播放真实 TTS。`,
    lastError: null,
    updatedAt: nowIso(),
    mock: true
  };
}

export async function mockEdgeControl(path: string) {
  await delay(300);
  return {
    status: "dry-run",
    path,
    executed: false,
    dryRun: true,
    message: "演示模式：动作已记录，未执行真实硬件控制。",
    updatedAt: nowIso(),
    mock: true
  };
}
