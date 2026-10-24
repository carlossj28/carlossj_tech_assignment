// "Add to my calendar" for a booked interview. A .ics is plain text every calendar app
// understands; the time is "floating" (no zone), like the slots themselves (ADR-032).

const DURATION_MIN = 30; // mirrors back/agent/data/slots.json

const stamp = (iso: string) => iso.replace(/[-:]/g, "").slice(0, 13) + "00"; // 2026-11-05T10:00 → 20261105T100000

export function icsHref(interviewAt: string, uid: string): string {
  const now = new Date().toISOString().slice(0, 16);
  const ics = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Grupo Sazon//Rita//ES",
    "BEGIN:VEVENT",
    `UID:${uid}@gruposazon`,
    `DTSTAMP:${stamp(now)}`,
    `DTSTART:${stamp(interviewAt)}`,
    `DURATION:PT${DURATION_MIN}M`,
    "SUMMARY:Entrevista con Grupo Sazón (repartidor/a)",
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");
  return `data:text/calendar;charset=utf-8,${encodeURIComponent(ics)}`;
}

// Fallback when no slot fitted (demo: the Calendly landing).
export const CALENDLY_URL = process.env.NEXT_PUBLIC_CALENDLY_URL ?? "https://calendly.com/";
