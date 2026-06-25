from fastapi import FastAPI, HTTPException

from app.agents.supervisor import SupervisorAgent
from app.config import get_settings
from app.schemas import AgentChatRequest, AgentChatResponse, HealthResponse

settings = get_settings()
supervisor = SupervisorAgent()

app = FastAPI(title="SmartPI Agent Orchestrator", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        rag_base_url=settings.rag_base_url,
        openclaw_configured=bool(settings.openclaw_base_url),
    )


@app.post("/api/v1/agent/chat", response_model=AgentChatResponse)
def agent_chat(request: AgentChatRequest) -> AgentChatResponse:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    try:
        return supervisor.run(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
