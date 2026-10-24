import Link from "next/link";
import { useState } from "react";
import PhoneIcon from "../ui/PhoneIcon";
import styles from "./chat.module.css";

// Text input + send, and the way into the voice call next to them (an icon on phones).
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
        placeholder="Escribe aquí…"
        aria-label="Tu respuesta"
        disabled={disabled}
        maxLength={2000} // back rejects longer messages (422)
        autoFocus
      />
      <Link className={styles.voice} href="/voz" aria-label="Llamar a Rita">
        <PhoneIcon />
        <span className={styles.voiceText}>Llamar</span>
      </Link>
      <button className={styles.send} type="submit" disabled={disabled || !text.trim()}>
        Enviar
        <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden>
          <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" />
        </svg>
      </button>
    </form>
  );
}
