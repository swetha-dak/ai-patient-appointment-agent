export type ChatRole = "user" | "assistant";

export type ToolCall = {
  name: string;
  args: Record<string, unknown>;
  ok?: boolean | null;
};

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  toolCalls?: ToolCall[];
};

export type ChatRequest = {
  session_id: string;
  message: string;
};

export type ChatResponse = {
  session_id: string;
  response: string;
  tool_calls: ToolCall[];
  status: string;
};

export type HealthResponse = {
  status: string;
  service: string;
  phase: number;
  database_path: string;
  ollama_base_url: string;
  ollama_model: string;
};
