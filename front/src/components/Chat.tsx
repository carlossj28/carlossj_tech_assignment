"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "@/lib/api";
import Composer from "./Composer";
import MessageList, { type Message } from "./MessageList";
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

  // Each new message restarts the silence timer; it only runs while Rita waits for the candidate.
  useEffect(() => {
    const waiting = conversationId && !completed && !typing && messages.at(-1)?.role === "rita";
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

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <span className={styles.tag}>✦ Grupo Sazón · Repartidores</span>
        <h1 className={styles.title}>Habla con Rita</h1>
        <p className={styles.lead}>Unas preguntas rápidas sobre tu candidatura. Tardas menos de 5 minutos.</p>
      </header>

      <section className={styles.card}>
        <MessageList messages={messages} typing={typing} />
        {error && (
          <p className={styles.error} role="alert">
            {error} {!conversationId && <button onClick={start}>Reintentar</button>}
          </p>
        )}
        {completed ? (
          <p className={styles.done}>
            <span className={styles.tag}>Entrevista completada</span> Gracias, un reclutador revisará tu candidatura.
          </p>
        ) : (
          <Composer disabled={!conversationId || typing} onSend={send} />
        )}
      </section>
    </main>
  );
}
