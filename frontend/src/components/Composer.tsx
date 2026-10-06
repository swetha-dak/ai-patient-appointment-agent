import { FormEvent } from "react";

type ComposerProps = {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
};

export default function Composer({ value, disabled, onChange, onSubmit }: ComposerProps) {
  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor="chat-input">
        Message
      </label>
      <textarea
        id="chat-input"
        rows={2}
        value={value}
        disabled={disabled}
        placeholder="Example: I need an appointment with Dr. Smith. I am PAT-002."
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            onSubmit();
          }
        }}
      />
      <button type="submit" disabled={disabled || value.trim().length === 0}>
        Send
      </button>
    </form>
  );
}
