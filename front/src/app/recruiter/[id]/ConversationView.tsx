"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import MessageList from "@/components/MessageList";
import StatusPill from "@/components/StatusPill";
import { FIELDS, KNOCKOUT, formatDate, formatField } from "@/lib/labels";
import { type ConversationDetail, getConversation } from "@/lib/recruiter";
import styles from "../recruiter.module.css";

export default function ConversationView() {
  const { id } = useParams<{ id: string }>();
  const [conv, setConv] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getConversation(id).then(setConv, () => setError(true));
  }, [id]);

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.ghost} href="/recruiter">← Candidaturas</Link>
        {conv && (
          <>
            <h1 className={styles.title}>{conv.candidate_name ?? "Sin nombre"}</h1>
            <span className={styles.meta}>
              <StatusPill status={conv.screening_status} />
              {conv.knockout_reason && <span className={styles.chip}>{KNOCKOUT[conv.knockout_reason]}</span>}
              <span className={styles.chip}>{conv.source === "voice" ? "Voz" : "Chat"}</span>
              {conv.inactive && <span className={styles.chip}>Inactivo</span>}
              <span className={styles.muted}>Última actividad {formatDate(conv.last_activity_at)}</span>
            </span>
          </>
        )}
      </header>

      {error && <p className={styles.error}>No hemos podido cargar la conversación.</p>}

      {conv && (
        <div className={styles.detail}>
          <section className={styles.panel}>
            <h2 className={styles.subtitle}>Datos</h2>
            <dl className={styles.fields}>
              {FIELDS.map(([key, label]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{formatField(key, conv.extracted_fields[key])}</dd>
                </div>
              ))}
            </dl>
            <h2 className={styles.subtitle}>Resumen de Rita</h2>
            <p className={conv.summary ? undefined : styles.muted}>{conv.summary ?? "Todavía sin resumen."}</p>
          </section>

          <section className={styles.panel}>
            <h2 className={styles.subtitle}>Conversación</h2>
            <MessageList messages={conv.turns.map((t) => ({ role: t.role === "user" ? "candidate" : "rita", text: t.content }))} />
          </section>
        </div>
      )}
    </main>
  );
}
