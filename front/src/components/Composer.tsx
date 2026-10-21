import { useState } from "react";
import styles from "./chat.module.css";

// Text input + send. Voice will add a mic button next to it.
export default function Composer({ disabled, onSend }: { disabled: boolean; onSend: (text: string) => Promise<boolean> }) {
  const [text, setText] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    setText("");
    if (!(await onSend(value))) setText(value); // keep the text so the candidate can retry
  }

  return (
    <form className={styles.composer} onSubmit={submit}>
      <input
        className={styles.input}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Escribe tu respuesta…"
        aria-label="Tu respuesta"
        disabled={disabled}
        autoFocus
      />
      <button className={styles.send} type="submit" disabled={disabled || !text.trim()}>
        Enviar
      </button>
    </form>
  );
}
