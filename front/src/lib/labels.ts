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
  ["contact_email", "Email"],
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
