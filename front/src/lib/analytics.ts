// Panel analytics, computed from the conversation list the panel already loads.
// Pure functions: rows in, numbers out (the page only draws them).

import type { Status } from "./api";
import type { ConversationRow } from "./recruiter";

export type Day = { date: string } & Record<Status, number>;

export type Analytics = {
  funnel: { started: number; completed: number; qualified: number };
  knockouts: { no_license: number; out_of_service_area: number };
  cities: { city: string; total: number; qualified: number }[];
  channels: { chat: number; voice: number };
  avgMinutes: number | null; // first to last message of the closed interviews
  daily: Day[];
};

const DAYS = 14;

export function analyze(rows: ConversationRow[], today = new Date()): Analytics {
  const count = (test: (r: ConversationRow) => boolean) => rows.filter(test).length;
  const completed = rows.filter((r) => r.completed);
  const minutes = completed.map((r) => (Date.parse(r.last_activity_at) - Date.parse(r.created_at)) / 60_000);

  return {
    funnel: { started: rows.length, completed: completed.length, qualified: count((r) => r.screening_status === "qualified") },
    knockouts: {
      no_license: count((r) => r.knockout_reason === "no_license"),
      out_of_service_area: count((r) => r.knockout_reason === "out_of_service_area"),
    },
    cities: byCity(rows),
    channels: { chat: count((r) => r.source === "chat"), voice: count((r) => r.source === "voice") },
    avgMinutes: minutes.length ? Math.round(minutes.reduce((a, b) => a + b, 0) / minutes.length) : null,
    daily: byDay(rows, today),
  };
}

// Top 5 cities by conversations; ties keep alphabetical order.
function byCity(rows: ConversationRow[]) {
  const cities = new Map<string, { city: string; total: number; qualified: number }>();
  for (const r of rows) {
    if (!r.city) continue;
    const c = cities.get(r.city) ?? { city: r.city, total: 0, qualified: 0 };
    c.total++;
    if (r.screening_status === "qualified") c.qualified++;
    cities.set(r.city, c);
  }
  return [...cities.values()].sort((a, b) => b.total - a.total || a.city.localeCompare(b.city)).slice(0, 5);
}

// The last DAYS days, oldest first, by the day each conversation started (local time).
function byDay(rows: ConversationRow[], today: Date): Day[] {
  const days = Array.from({ length: DAYS }, (_, i) => {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (DAYS - 1 - i));
    return { date: localDate(d), qualified: 0, pending: 0, disqualified: 0 };
  });
  const index = new Map(days.map((d, i) => [d.date, i]));
  for (const r of rows) {
    const i = index.get(localDate(new Date(r.created_at)));
    if (i !== undefined) days[i][r.screening_status]++;
  }
  return days;
}

const localDate = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
