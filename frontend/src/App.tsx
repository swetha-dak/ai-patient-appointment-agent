import { useEffect, useMemo, useState } from "react";
import { fetchHealth, sendChat } from "./api";
import Composer from "./components/Composer";
import MessageList from "./components/MessageList";
import type { ChatMessage, HealthResponse } from "./types";
import "./styles/app.css";

const SESSION_KEY = "appointment-session-id";

function getOrCreateSessionId(): string {
  const existing = sessionStorage.getItem(SESSION_KEY);
  if (existing && existing !== "demo-session-001") {
    return existing;
  }
  const created =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? `demo-session-${crypto.randomUUID()}`
      : `demo-session-${Date.now()}`;
  sessionStorage.setItem(SESSION_KEY, created);
  return created;
}

export default function App() {
  const sessionId = useMemo(() => getOrCreateSessionId(), []);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then((payload) => {
        if (!cancelled) {
          setHealth(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Cannot reach the backend. Start FastAPI on port 8000.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSend() {
    const text = draft.trim();
    if (!text || loading) {
      return;
    }
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
    };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setLoading(true);
    setError(null);
    try {
      const payload = await sendChat({ session_id: sessionId, message: text });
      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: payload.response || "(empty response)",
        toolCalls: payload.tool_calls,
      };
      setMessages((current) => [...current, assistantMessage]);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Chat request failed.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app">
      <header>
        <h1>Patient appointment agent</h1>
        <p className="meta">
          Session {sessionId}
          {health ? ` · backend phase ${health.phase}` : ""}
        </p>
      </header>
      {error ? <p className="error">{error}</p> : null}
      <MessageList messages={messages} loading={loading} />
      <Composer value={draft} disabled={loading} onChange={setDraft} onSubmit={() => void handleSend()} />
    </main>
  );
}
