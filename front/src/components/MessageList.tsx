import { useEffect, useRef } from "react";
import styles from "./chat.module.css";

export type Message = { role: "rita" | "candidate"; text: string };

// Pure view of the conversation; voice will reuse it for the live transcript.
export default function MessageList({ messages, typing }: { messages: Message[]; typing: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages, typing]);

  return (
    <div className={styles.messages} aria-live="polite">
      {messages.map((m, i) => (
        <p key={i} className={`${styles.bubble} ${styles[m.role]}`} data-role={m.role}>
          {m.text}
        </p>
      ))}
      {typing && <p className={styles.typing}>Rita está escribiendo…</p>}
      <div ref={end} />
    </div>
  );
}
