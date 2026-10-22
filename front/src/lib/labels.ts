// Spanish labels for the recruiter panel. Keys mirror back/schemas.py.
import type { Status } from "./api";

export const STATUS: Record<Status, string> = {
  qualified: "Cualificado",
  pending: "Pendiente",
  disqualified: "Descartado",
};

export const KNOCKOUT = { no_license: "Sin carné de conducir", out_of_service_area: "Ciudad sin cobertura" };

const OPTIONS: Record<string, string> = {
  full_time: "Jornada completa", part_time: "Media jornada", weekends: "Fines de semana",
  morning: "Mañana", afternoon: "Tarde", evening: "Noche", flexible: "Flexible",
};

// Field order and labels as the recruiter reads them.
export const FIELDS: [key: string, label: string][] = [
  ["full_name", "Nombre"],
  ["has_driver_license", "Carné de conducir"],
  ["city", "Ciudad"],
  ["availability", "Disponibilidad"],
  ["preferred_schedule", "Horario"],
  ["prior_experience", "Experiencia"],
  ["start_date", "Fecha de inicio"],
];

export function formatField(key: string, value: unknown): string {
  if (value === undefined || value === null) return "—";
  if (typeof value === "boolean") return value ? "Sí" : "No";
  if (Array.isArray(value)) return value.map((v) => OPTIONS[v] ?? v).join(", ");
  if (key === "prior_experience") {
    const { years, platforms } = value as { years: number; platforms: string[] };
    if (!years && !platforms.length) return "Sin experiencia";
    return [`${years} ${years === 1 ? "año" : "años"}`, ...platforms].join(" · ");
  }
  if (key === "start_date") return formatDate(String(value), false);
  return String(value);
}

export function formatDate(iso: string, withTime = true): string {
  return new Date(iso).toLocaleString("es-ES", withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" });
}

const RELATIVE = new Intl.RelativeTimeFormat("es-ES", { numeric: "auto" });

// "hace 5 minutos", "ayer"…: quick to scan in the list; formatDate keeps the exact time.
export function formatRelative(iso: string): string {
  const minutes = Math.round((new Date(iso).getTime() - Date.now()) / 60_000);
  if (minutes > -1) return "ahora mismo";
  if (minutes > -60) return RELATIVE.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (hours > -24) return RELATIVE.format(hours, "hour");
  return RELATIVE.format(Math.round(hours / 24), "day");
}

// Time between two instants, rounded to minutes: "5 min", "1 h 20 min".
export function formatDuration(fromIso: string, toIso: string): string {
  const minutes = Math.max(1, Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 60_000));
  if (minutes < 60) return `${minutes} min`;
  const rest = minutes % 60;
  return rest ? `${Math.floor(minutes / 60)} h ${rest} min` : `${minutes / 60} h`;
}
