"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Aurora from "@/components/Aurora";
import Avatar from "@/components/Avatar";
import Brand from "@/components/Brand";
import MessageList from "@/components/MessageList";
import Orb from "@/components/Orb";
import StatusPill from "@/components/StatusPill";
import { FIELDS, KNOCKOUT, SENTIMENT, formatDate, formatDuration, formatField, formatRelative } from "@/lib/labels";
import { type ConversationDetail, getConversation } from "@/lib/recruiter";
import shared from "../recruiter.module.css";
import styles from "./detail.module.css";

export default function ConversationView() {
  const { id } = useParams<{ id: string }>();
  const [conv, setConv] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getConversation(id).then(setConv, () => setError(true));
  }, [id]);

  const captured = conv ? FIELDS.filter(([key]) => conv.extracted_fields[key] != null).length : 0;

  return (
    <main className={shared.page}>
      <Aurora variant="quiet" />
      <header className={shared.bar}>
        <Brand area="Reclutadores" />
        <Link className={shared.ghost} href="/recruiter" aria-label="Candidaturas">
          <svg viewBox="0 0 16 16" aria-hidden>
            <path d="M13 8H3M7.5 3.5 3 8l4.5 4.5" />
          </svg>
          <span className={shared.buttonText}>Candidaturas</span>
        </Link>
      </header>

      {error && <p className={shared.error}>No hemos podido cargar la conversación.</p>}
      {!conv && !error && <div className={shared.skeleton} aria-hidden />}

      {conv && (
        <>
          <section className={`${shared.panel} ${styles.profile}`}>
            <Avatar name={conv.candidate_name} size={72} />
            <div className={styles.identity}>
              <h1 className={styles.name}>{conv.candidate_name ?? "Sin nombre"}</h1>
              <span className={shared.tags}>
                <StatusPill status={conv.screening_status} />
                {conv.knockout_reason && <span className={`${shared.chip} ${styles.reason}`}>{KNOCKOUT[conv.knockout_reason]}</span>}
                <span className={shared.chip}>{conv.source === "voice" ? "Voz" : "Chat"}</span>
                {conv.inactive && <span className={`${shared.chip} ${shared.idle}`}>Inactivo</span>}
              </span>
            </div>
            <Completeness done={captured} total={FIELDS.length} />
            <div className={styles.facts}>
              <span>
                <small className="eyebrow">Inicio</small>
                {formatDate(conv.created_at)}
              </span>
              <span>
                <small className="eyebrow">Duración</small>
                {formatDuration(conv.created_at, conv.last_activity_at)}
              </span>
              <span>
                <small className="eyebrow">Última actividad</small>
                <time dateTime={conv.last_activity_at} title={formatDate(conv.last_activity_at)}>
                  {formatRelative(conv.last_activity_at)}
                </time>
              </span>
            </div>
          </section>

          <div className={styles.columns}>
            <div className={styles.stack}>
              <section className={`${shared.panel} ${conv.summary ? styles.summary : ""}`}>
                <h2 className={styles.heading}>
                  <Orb size={22} /> Resumen de Rita
                </h2>
                {conv.sentiment === "frustrated" && (
                  <p className={`${shared.error} ${styles.alert}`} role="note">
                    El candidato se mostró frustrado. Revisa la conversación antes de contactarle.
                  </p>
                )}
                {conv.summary ? (
                  <figure className={styles.quote}>
                    <blockquote>{conv.summary}</blockquote>
                    <figcaption>
                      — Rita, asistente de selección
                      {conv.sentiment && (
                        <span className={`${shared.status} ${styles[conv.sentiment]}`}>
                          <span className={shared.dot} aria-hidden />
                          Tono: {SENTIMENT[conv.sentiment]}
                        </span>
                      )}
                    </figcaption>
                  </figure>
                ) : (
                  <p className={shared.muted}>Todavía sin resumen.</p>
                )}
              </section>

              <section className={shared.panel}>
                <h2 className={styles.heading}>Datos capturados</h2>
                <dl className={styles.fields}>
                  {FIELDS.map(([key, label]) => (
                    <div key={key} className={conv.extracted_fields[key] == null ? styles.missing : undefined}>
                      <dt>{label}</dt>
                      <dd>{formatField(key, conv.extracted_fields[key])}</dd>
                    </div>
                  ))}
                  {/* Booked by Rita; its own column, not a candidate answer (ADR-032). */}
                  <div className={conv.interview_at ? undefined : styles.missing}>
                    <dt>Entrevista</dt>
                    <dd>{conv.interview_at ? formatDate(conv.interview_at) : "Sin reservar"}</dd>
                  </div>
                </dl>
              </section>
            </div>

            <section className={`${shared.panel} ${styles.log}`}>
              <h2 className={styles.heading}>
                Conversación <span className={`${shared.count} ${styles.aside}`}>{conv.turns.length} mensajes</span>
              </h2>
              <MessageList messages={conv.turns.map((t) => ({ role: t.role === "user" ? "candidate" : "rita", text: t.content }))} transcript />
            </section>
          </div>
        </>
      )}
    </main>
  );
}

// Ring that fills with the fields Rita has captured (track: a lighter step of the same hue).
// pathLength 1: the dash is the captured share, whatever the radius.
function Completeness({ done, total }: { done: number; total: number }) {
  return (
    <div className={styles.ring} role="img" aria-label={`${done} de ${total} datos capturados`}>
      <svg viewBox="0 0 100 100">
        <defs>
          <linearGradient id="completeness" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" style={{ stopColor: "var(--violet)" }} />
            <stop offset="0.55" style={{ stopColor: "var(--coral)" }} />
            <stop offset="1" style={{ stopColor: "var(--amber)" }} />
          </linearGradient>
        </defs>
        <circle className={styles.track} cx="50" cy="50" r="42" />
        {/* Nothing captured: no arc at all (a zero-length dash still draws a round cap). */}
        {done > 0 && <circle className={styles.progress} cx="50" cy="50" r="42" pathLength={1} strokeDasharray={`${done / total} 1`} />}
      </svg>
      <span className={styles.ringValue}>
        <strong>{done}</strong>/{total}
      </span>
      <span className={`${styles.ringLabel} eyebrow`}>datos</span>
    </div>
  );
}
