"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Aurora from "@/components/Aurora";
import Avatar from "@/components/Avatar";
import Brand from "@/components/Brand";
import Orb from "@/components/Orb";
import StatusPill from "@/components/StatusPill";
import { login } from "@/lib/recruiter";
import shared from "../recruiter.module.css";
import styles from "./login.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (await login(String(form.get("username")), String(form.get("password")))) router.push("/recruiter");
    else setError(true);
  }

  return (
    <main className={styles.split}>
      <Aurora variant="quiet" />
      <section className={styles.art}>
        <Aurora variant="panel" />
        <Brand area="Reclutadores" />
        {/* A glimpse of the product, from question to verdict: decoration only. */}
        <div className={styles.glimpses} aria-hidden>
          <div className={`${styles.glimpse} ${styles.ask}`}>
            <Orb size={32} active />
            <span>
              <strong>Rita</strong>
              ¿Tienes carné de conducir en vigor?
            </span>
          </div>
          <div className={`${styles.glimpse} ${styles.brief}`}>
            <span className={styles.briefHead}>
              <Orb size={20} still />
              <strong>Resumen de Rita</strong>
              <small className="eyebrow">7/8 datos</small>
            </span>
            <p>Repartidora con 2 años en Glovo. Vive en Madrid y busca jornada completa.</p>
          </div>
          <div className={`${styles.glimpse} ${styles.verdict}`}>
            <Avatar name="Marta Gil" size={32} />
            <span>
              <strong>Marta Gil</strong>
              Madrid · 2 años de experiencia
            </span>
            <StatusPill status="qualified" />
          </div>
        </div>
        <div className={styles.pitch}>
          <p className={styles.headline}>
            Rita entrevista.
            <br />
            <span>Tú decides.</span>
          </p>
          <p className={styles.sub}>Cada candidatura llega cribada, resumida y lista para revisar.</p>
        </div>
      </section>

      <section className={styles.side}>
        <form className={styles.form} onSubmit={submit}>
          <header className={styles.head}>
            <span className={shared.kicker}>Panel de reclutamiento</span>
            <h1 className={styles.title}>Acceso</h1>
            <p className={shared.muted}>Entra para revisar las conversaciones de Rita con los candidatos.</p>
          </header>
          <label className={shared.label}>
            Usuario
            <input className={shared.field} name="username" autoComplete="username" required autoFocus />
          </label>
          <label className={shared.label}>
            Contraseña
            <input className={shared.field} name="password" type="password" autoComplete="current-password" required />
          </label>
          {error && (
            <p className={shared.error} role="alert">
              Usuario o contraseña incorrectos.
            </p>
          )}
          <button className={shared.primary} type="submit">
            Entrar
            <svg className={styles.icon} viewBox="0 0 16 16" aria-hidden>
              <path d="M3 8h10M8.5 3.5 13 8l-4.5 4.5" />
            </svg>
          </button>
          <p className={styles.secure}>
            <svg className={styles.icon} viewBox="0 0 16 16" aria-hidden>
              <rect x="3.5" y="7" width="9" height="6.5" rx="1.5" />
              <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
            </svg>
            Acceso solo para el equipo de selección
          </p>
        </form>
        <p className={styles.foot}>
          ¿Buscas trabajo de repartidor? <Link href="/">Habla con Rita</Link>
        </p>
      </section>
    </main>
  );
}
