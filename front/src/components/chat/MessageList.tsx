import { useEffect, useRef } from "react";
import Orb from "../ui/Orb";
import styles from "./chat.module.css";

export type Message = { role: "rita" | "candidate"; text: string };

// Pure view of the conversation; voice will reuse it for the live transcript.
// Only the bubbles carry data-role: avatars and the typing dots are decoration.
// `transcript`: the recruiter's read-only copy, with still orbs and the candidate's answers stressed.
export default function MessageList({
  messages,
  typing = false,
  transcript = false,
}: {
  messages: Message[];
  typing?: boolean;
  transcript?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  // Scroll only this box (not the page) so the latest message stays in view.
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [messages, typing]);

  return (
    <div ref={box} className={`${styles.messages} ${transcript ? styles.transcript : ""}`} aria-live="polite">
      {messages.map((m, i) => {
        // Bubbles group into runs per speaker; Rita's orb sits only on the last one of each run.
        const next = messages[i + 1]?.role ?? (typing ? "rita" : undefined);
        const last = next !== m.role;
        return (
          <div key={i} className={`${styles.row} ${styles[m.role]} ${last ? styles.last : ""}`}>
            {m.role === "rita" && (last ? <Orb size={transcript ? 22 : 28} still={transcript} /> : <span className={styles.gutter} />)}
            <p className={styles.bubble} data-role={m.role}>
              {m.text}
            </p>
          </div>
        );
      })}
      {typing && (
        <div className={`${styles.row} ${styles.rita} ${styles.last}`}>
          <Orb active />
          <span className={styles.typing}>
            <i />
            <i />
            <i />
            <span className="sr-only">Rita está escribiendo…</span>
          </span>
        </div>
      )}
    </div>
  );
}
