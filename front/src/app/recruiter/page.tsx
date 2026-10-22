"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { Status } from "@/lib/api";
import Aurora from "@/components/Aurora";
import Avatar from "@/components/Avatar";
import Brand from "@/components/Brand";
import Orb from "@/components/Orb";
import StatusPill from "@/components/StatusPill";
import { KNOCKOUT, STATUS, formatDate, formatRelative } from "@/lib/labels";
import { type ConversationRow, listConversations, logout } from "@/lib/recruiter";
import styles from "./recruiter.module.css";

const FILTERS: (Status | "all")[] = ["all", "qualified", "pending", "disqualified"];

export default function ConversationsPage() {
  const [rows, setRows] = useState<ConversationRow[] | null>(null);
  const [filter, setFilter] = useState<Status | "all">("all");
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setError(false);
    try {
      setRows(await listConversations());
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const count = (f: Status | "all") => rows?.filter((r) => f === "all" || r.screening_status === f).length ?? 0;
  const shown = rows?.filter((r) => filter === "all" || r.screening_status === filter) ?? [];

  return (
    <main className={styles.page}>
      <Aurora variant="quiet" />
      <header className={styles.bar}>
        <Brand area="Reclutadores" />
        <span className={styles.actions}>
          <button className={styles.ghost} onClick={load} aria-label="Actualizar">
            <svg viewBox="0 0 16 16" aria-hidden>
              <path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9M13.5 2.5v3h-3" />
            </svg>
            <span className={styles.buttonText}>Actualizar</span>
          </button>
          <button className={styles.ghost} onClick={logout} aria-label="Cerrar sesión">
            <svg viewBox="0 0 16 16" aria-hidden>
              <path d="M6 2.5H3.5v11H6M10 5l3 3-3 3M13 8H6.5" />
            </svg>
            <span className={styles.buttonText}>Cerrar sesión</span>
          </button>
        </span>
      </header>

      <section className={styles.intro}>
        <span className={styles.kicker}>Panel de reclutamiento</span>
        <h1 className={styles.title}>Candidaturas</h1>
        <p className={styles.lead}>Cada conversación con Rita llega aquí con su estado, los datos que ha recogido y un resumen.</p>
      </section>

      <Stats rows={rows} error={error} />

      <nav className={styles.tabs} aria-label="Filtrar por estado">
        {FILTERS.map((f) => (
          <button key={f} className={styles.tab} aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {f !== "all" && <span className={`${styles.dot} ${styles[f]}`} aria-hidden />}
            {f === "all" ? "Todas" : STATUS[f]} {rows && <span className={styles.count}>{count(f)}</span>}
          </button>
        ))}
      </nav>

      {error && <p className={styles.error}>No hemos podido cargar las conversaciones.</p>}
      {!rows && !error && <div className={styles.skeleton} aria-hidden />}
      {rows && !shown.length && (
        <div className={styles.empty}>
          <Orb size={40} />
          <p>No hay conversaciones.</p>
          <span className={styles.muted}>Cuando un candidato hable con Rita, aparecerá aquí.</span>
        </div>
      )}

      {/* One glass table: header and rows split by hairlines (a single surface, cheap to scroll). */}
      {shown.length > 0 && (
        <div className={styles.table}>
          <div className={`${styles.columns} eyebrow`} aria-hidden>
            <span>Candidato</span>
            <span>Estado</span>
            <span>Conversación</span>
            <span>Última actividad</span>
          </div>
          <ul className={styles.list}>
            {shown.map((r, i) => (
              <li key={r.id} style={{ "--i": i } as React.CSSProperties}>
                <Link className={styles.row} href={`/recruiter/${r.id}`}>
                  <Avatar name={r.candidate_name} size={36} />
                  <span className={styles.who}>
                    <span className={styles.name}>{r.candidate_name ?? "Sin nombre"}</span>
                    {r.knockout_reason && <span className={styles.note}>{KNOCKOUT[r.knockout_reason]}</span>}
                  </span>
                  <span className={styles.state}>
                    <StatusPill status={r.screening_status} />
                  </span>
                  <span className={styles.tags}>
                    <span className={styles.chip}>{r.source === "voice" ? "Voz" : "Chat"}</span>
                    {r.inactive && <span className={`${styles.chip} ${styles.idle}`}>Inactivo</span>}
                    {r.completed && <span className={styles.chip}>Completada</span>}
                  </span>
                  <time className={styles.when} dateTime={r.last_activity_at} title={formatDate(r.last_activity_at)}>
                    {formatRelative(r.last_activity_at)}
                  </time>
                  <svg className={styles.arrow} viewBox="0 0 16 16" aria-hidden>
                    <path d="M6 3.5 10.5 8 6 12.5" />
                  </svg>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </main>
  );
}

// Bento of headline numbers, computed from the whole list (not the active filter).
function Stats({ rows, error }: { rows: ConversationRow[] | null; error: boolean }) {
  const total = rows?.length ?? 0;
  const qualified = countWhere(rows, (r) => r.screening_status === "qualified");
  const share = total ? Math.round((qualified / total) * 100) : 0;
  const tiles = [
    { tone: "violet", label: "Candidaturas", value: total, note: "en total" },
    { tone: "mint", label: "Cualificadas", value: share, unit: "%", note: `${qualified} de ${total}`, meter: share },
    { tone: "amber", label: "Pendientes", value: countWhere(rows, (r) => r.screening_status === "pending"), note: "sin decisión todavía" },
    { tone: "slate", label: "Inactivas", value: countWhere(rows, (r) => r.inactive), note: "más de 5 min sin responder" },
  ];

  return (
    <dl className={styles.stats}>
      {tiles.map((t, i) => (
        <div key={t.label} className={styles.stat} data-tone={t.tone} style={{ "--i": i } as React.CSSProperties}>
          <dt>{t.label}</dt>
          <dd className={styles.value}>
            {rows ? t.value : "—"}
            {rows && t.unit && <small>{t.unit}</small>}
          </dd>
          {t.meter !== undefined && (
            <dd className={styles.meter} aria-hidden>
              <span style={{ width: `${t.meter}%` }} />
            </dd>
          )}
          <dd className={styles.statNote}>{rows ? t.note : error ? "Sin datos" : "Cargando…"}</dd>
        </div>
      ))}
    </dl>
  );
}

const countWhere = (rows: ConversationRow[] | null, test: (r: ConversationRow) => boolean) => rows?.filter(test).length ?? 0;
