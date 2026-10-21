"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { Status } from "@/lib/api";
import StatusPill from "@/components/StatusPill";
import { STATUS, formatDate } from "@/lib/labels";
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
      <header className={styles.header}>
        <div className={styles.toolbar}>
          <span className={styles.tag}>✦ Grupo Sazón · Reclutadores</span>
          <span className={styles.actions}>
            <button className={styles.ghost} onClick={load}>Actualizar</button>
            <button className={styles.ghost} onClick={logout}>Cerrar sesión</button>
          </span>
        </div>
        <h1 className={styles.title}>Candidaturas</h1>
      </header>

      <nav className={styles.tabs} aria-label="Filtrar por estado">
        {FILTERS.map((f) => (
          <button key={f} className={styles.tab} aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {f === "all" ? "Todas" : STATUS[f]} <span className={styles.count}>{count(f)}</span>
          </button>
        ))}
      </nav>

      {error && <p className={styles.error}>No hemos podido cargar las conversaciones.</p>}
      {rows && !shown.length && <p className={styles.muted}>No hay conversaciones.</p>}

      <ul className={styles.list}>
        {shown.map((r) => (
          <li key={r.id}>
            <Link className={styles.row} href={`/recruiter/${r.id}`}>
              <span className={styles.name}>{r.candidate_name ?? "Sin nombre"}</span>
              <span className={styles.meta}>
                <StatusPill status={r.screening_status} />
                <span className={styles.chip}>{r.source === "voice" ? "Voz" : "Chat"}</span>
                {r.inactive && <span className={styles.chip}>Inactivo</span>}
                {r.completed && <span className={styles.chip}>Completada</span>}
                <span className={styles.muted}>{formatDate(r.last_activity_at)}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
