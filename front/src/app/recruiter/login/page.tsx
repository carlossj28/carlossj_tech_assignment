"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { login } from "@/lib/recruiter";
import styles from "../recruiter.module.css";

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
    <main className={`${styles.page} ${styles.narrow}`}>
      <header className={styles.header}>
        <span className={styles.tag}>✦ Grupo Sazón · Reclutadores</span>
        <h1 className={styles.title}>Acceso</h1>
      </header>
      <form className={styles.panel} onSubmit={submit}>
        <label className={styles.label}>
          Usuario
          <input className={styles.field} name="username" autoComplete="username" required autoFocus />
        </label>
        <label className={styles.label}>
          Contraseña
          <input className={styles.field} name="password" type="password" autoComplete="current-password" required />
        </label>
        {error && <p className={styles.error}>Usuario o contraseña incorrectos.</p>}
        <button className={styles.primary} type="submit">
          Entrar
        </button>
      </form>
    </main>
  );
}
