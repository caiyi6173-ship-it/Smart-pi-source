export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly payload?: unknown
  ) {
    super(message);
  }
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const startedAt = performance.now();
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    },
    ...init
  });

  const text = await response.text();
  const payload = text ? safeJson(text) : null;
  if (!response.ok) {
    throw new ApiError(`HTTP ${response.status} ${path}`, response.status, payload);
  }

  if (payload && typeof payload === "object") {
    return {
      ...(payload as Record<string, unknown>),
      __clientLatencyMs: Math.round(performance.now() - startedAt)
    } as T;
  }
  return payload as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
