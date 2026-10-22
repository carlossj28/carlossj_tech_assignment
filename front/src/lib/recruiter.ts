// Recruiter panel API (see project memory "chat-api-contract"). The session is a
// signed HttpOnly cookie set by the back on login (ADR-011); fetch sends it on its own.

import type { Status } from "./api";

export type ConversationRow = {
  id: string;
  candidate_name: string | null;
  city: string | null;
  source: "chat" | "voice";
  screening_status: Status;
  knockout_reason: "no_license" | "out_of_service_area" | null;
  completed: boolean;
  inactive: boolean;
  created_at: string;
  last_activity_at: string;
};

export type ConversationDetail = ConversationRow & {
  extracted_fields: Record<string, unknown>;
  summary: string | null;
  turns: { role: "user" | "assistant"; content: string; created_at: string }[];
};

const LOGIN = "/recruiter/login";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (res.status === 401) {
    window.location.assign(LOGIN); // no session or expired: back to the login page
    return new Promise<T>(() => {}); // never resolves; the page is going away
  }
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

export const listConversations = () => get<ConversationRow[]>("/api/recruiter/conversations");

export const getConversation = (id: string) => get<ConversationDetail>(`/api/recruiter/conversations/${id}`);

export async function login(username: string, password: string): Promise<boolean> {
  const res = await fetch("/api/recruiter/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return res.ok;
}

export async function logout(): Promise<void> {
  await fetch("/api/recruiter/logout", { method: "POST" });
  window.location.assign(LOGIN);
}
