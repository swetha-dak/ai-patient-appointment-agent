import type { ChatMessage } from "../types";

type MessageListProps = {
  messages: ChatMessage[];
  loading: boolean;
};

export default function MessageList({ messages, loading }: MessageListProps) {
  if (messages.length === 0 && !loading) {
    return (
      <div className="empty">
        Ask to book, cancel, or reschedule a fictional clinic appointment.
      </div>
    );
  }

  return (
    <ol className="messages">
      {messages.map((message) => (
        <li key={message.id} className={`bubble ${message.role}`}>
          <p>{message.content}</p>
          {message.toolCalls && message.toolCalls.length > 0 ? (
            <ul className="tools">
              {message.toolCalls.map((call, index) => (
                <li key={`${message.id}-tool-${index}`}>
                  {call.name}
                  {call.ok === false ? " (failed)" : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
      {loading ? (
        <li className="bubble assistant loading">Thinking…</li>
      ) : null}
    </ol>
  );
}
