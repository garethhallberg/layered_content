import { FormEvent, useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { Turn } from "../api/client";

interface Props {
  turns: Turn[];
  disabled: boolean;
  onSend: (content: string) => Promise<void>;
}

export function ChatPane({ turns, disabled, onSend }: Props) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns.length]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const content = draft.trim();
    if (!content) return;
    setDraft("");
    await onSend(content);
  };

  return (
    <section className="chat-pane">
      <div className="pane-header">
        <h2>Chat</h2>
      </div>
      <div className="turn-list" ref={scrollRef}>
        {turns.length === 0 && <div className="empty">Ask a question about the uploaded documents.</div>}
        {turns.map((turn) => (
          <article className={`turn ${turn.role}`} key={turn.id}>
            <div className="turn-role">{turn.role}</div>
            <p>{turn.content}</p>
            <span>{turn.token_count.toLocaleString()} tokens</span>
          </article>
        ))}
      </div>
      <form className="composer" onSubmit={submit}>
        <textarea
          value={draft}
          disabled={disabled}
          placeholder="Type a document-analysis question..."
          onChange={(event) => setDraft(event.target.value)}
        />
        <button className="send-button" type="submit" disabled={disabled || !draft.trim()} title="Send message">
          <Send size={18} />
        </button>
      </form>
    </section>
  );
}

