import type { ChatRequest, ChatResponse, HealthResponse } from "./types";

async function readError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload.detail) {
      return payload.detail;
    }
  } catch {
    /* ignore */
  }
  return `Request failed (${response.status})`;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch("/health");
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json() as Promise<HealthResponse>;
}

export async function sendChat(body: ChatRequest): Promise<ChatResponse> {
  const response = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json() as Promise<ChatResponse>;
}
