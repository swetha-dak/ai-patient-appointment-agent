from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ToolCallOut(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)
    ok: bool | None = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    tool_calls: list[ToolCallOut]
    status: str


class EvaluateRequest(BaseModel):
    scenario_ids: list[str] | None = None


class ImproveRequest(BaseModel):
    scenario_ids: list[str] | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    phase: int
    database_path: str
    ollama_base_url: str
    ollama_model: str
