import { useEffect, useRef } from "react";
import styles from "./chat.module.css";

export type Message = { role: "rita" | "candidate"; text: string };

// Pure view of the conversation; voice will reuse it for the live transcript.
export default function MessageList({ messages, typing = false }: { messages: Message[]; typing?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  // Scroll only this box (not the page) so the latest message stays in view.
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [messages, typing]);

  return (
    <div ref={box} className={styles.messages} aria-live="polite">
      {messages.map((m, i) => (
        <p key={i} className={`${styles.bubble} ${styles[m.role]}`} data-role={m.role}>
          {m.text}
        </p>
      ))}
      {typing && <p className={styles.typing}>Rita está escribiendo…</p>}
    </div>
  );
}
