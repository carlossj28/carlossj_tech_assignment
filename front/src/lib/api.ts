// Chat API contract with back/ (see project memory "chat-api-contract").

export type Status = "pending" | "qualified" | "disqualified";

async function post<T>(path: string, body?: object): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body && JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

export const startChat = () =>
  post<{ conversation_id: string; greeting: string }>("/api/chat/start");

export const sendMessage = (conversation_id: string, message: string) =>
  post<{ reply: string; completed: boolean; status: Status }>("/api/chat/message", { conversation_id, message });

export const nudge = (conversation_id: string) =>
  post<{ reply: string | null }>("/api/chat/nudge", { conversation_id });
