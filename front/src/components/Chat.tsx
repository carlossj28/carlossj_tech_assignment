"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "@/lib/api";
import { FIELDS } from "@/lib/labels";
import Aurora from "./Aurora";
import Brand from "./Brand";
import Composer from "./Composer";
import MessageList, { type Message } from "./MessageList";
import Orb from "./Orb";
import styles from "./chat.module.css";

const NUDGE_AFTER_MS = 60_000; // silence before asking Rita for a reminder (ADR-018)

export default function Chat() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [typing, setTyping] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nudgesDone = useRef(false); // back answered null: no more reminders
  const started = useRef(false); // dev StrictMode runs effects twice; open only one conversation

  const say = (role: Message["role"], text: string) => setMessages((m) => [...m, { role, text }]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const { conversation_id, greeting } = await api.startChat();
      setConversationId(conversation_id);
      say("rita", greeting);
    } catch {
      setError("No hemos podido iniciar la conversación.");
    }
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start();
  }, [start]);

  async function send(text: string): Promise<boolean> {
    if (!conversationId) return false;
    setError(null);
    say("candidate", text);
    setTyping(true);
    try {
      const res = await api.sendMessage(conversationId, text);
      say("rita", res.reply);
      setCompleted(res.completed);
      return true;
    } catch {
      setMessages((m) => m.slice(0, -1)); // drop the unsent bubble; Composer keeps the text
      setError("No hemos podido enviar tu mensaje. Inténtalo de nuevo.");
      return false;
    } finally {
      setTyping(false);
    }
  }

  // Each new message restarts the silence timer; it only runs while Rita waits for the candidate,
  // and only after their first message (before that the conversation doesn't exist in the back).
  useEffect(() => {
    const spoke = messages.some((m) => m.role === "candidate");
    const waiting = conversationId && spoke && !completed && !typing && messages.at(-1)?.role === "rita";
    if (!waiting || nudgesDone.current) return;
    const timer = setTimeout(async () => {
      try {
        const { reply } = await api.nudge(conversationId);
        if (reply) say("rita", reply);
        else nudgesDone.current = true;
      } catch {
        nudgesDone.current = true; // a reminder is optional; never show an error for it
      }
    }, NUDGE_AFTER_MS);
    return () => clearTimeout(timer);
  }, [conversationId, completed, typing, messages]);

  const offline = !conversationId && !!error;
  const writing = typing || (!conversationId && !error); // Rita also "writes" her greeting while it loads

  return (
    <main className={styles.page}>
      <Aurora />
      <header className={styles.bar}>
        <Brand area="Repartidores" />
        {/* Demo shortcut into the panel; on a phone it shrinks to an icon. */}
        <Link className={styles.staff} href="/recruiter/login" aria-label="Acceso reclutadores">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden>
            <circle cx="8" cy="5.5" r="2.5" />
            <path d="M3 13.5c.6-2.6 2.6-4 5-4s4.4 1.4 5 4" />
          </svg>
          <span className={styles.staffText}>Acceso reclutadores</span>
        </Link>
      </header>

      <div className={styles.layout}>
        <section className={styles.hero}>
          <span className={styles.tag}>
            <span className={styles.spark} aria-hidden>✦</span> Entrevista con IA
          </span>
          <h1 className={styles.title}>
            Habla con <span className={styles.glow}>Rita</span>
          </h1>
          <p className={styles.lead}>Unas preguntas rápidas sobre tu candidatura. Tardas menos de 5 minutos.</p>
          <div className={styles.topics}>
            <span className={styles.label}>Te preguntará por</span>
            <p>
              {FIELDS.map(([key, label]) => (
                <span key={key} className={styles.topic}>{label}</span>
              ))}
            </p>
          </div>
        </section>

        <section className={styles.card} aria-label="Conversación con Rita">
          <div className={styles.agent}>
            <Orb size={44} active={writing} />
            <span className={styles.who}>
              <strong>Rita</strong>
              <span>Asistente de selección</span>
            </span>
            <span className={`${styles.presence} eyebrow ${offline ? styles.offline : writing ? styles.busy : ""}`}>
              {offline ? "Sin conexión" : writing ? "Escribiendo…" : "En línea"}
            </span>
          </div>

          <MessageList messages={messages} typing={writing} />
          {error && (
            <p className={styles.error} role="alert">
              {error} {!conversationId && <button onClick={start}>Reintentar</button>}
            </p>
          )}
          {completed && (
            <p className={styles.done}>
              <svg className={styles.check} viewBox="0 0 32 32" aria-hidden>
                <circle cx="16" cy="16" r="15" />
                <path d="m10 16.5 4 4 8-9" pathLength={1} />
              </svg>
              <span>
                <strong>Entrevista completada</strong> Gracias, un reclutador revisará tu candidatura.
              </span>
            </p>
          )}
          {/* Stays enabled after completion: a new message reopens the conversation (ADR-028). */}
          <Composer disabled={!conversationId || typing} onSend={send} />
          <p className={styles.disclaimer}>Rita es una IA · Responde con tus palabras, sin prisa.</p>
        </section>
      </div>
    </main>
  );
}
