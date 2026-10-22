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

// ── Voice: the browser talks to OpenAI directly and relays here what must be stored.

export const voiceSession = () => post<{ conversation_id: string; client_secret: string }>("/api/voice/session");

// The tool result goes back to the model. Any failure (back down, 409, 500) becomes `error`,
// so Rita tells the candidate it's a technical problem instead of the call freezing.
export const voiceTool = (conversation_id: string, name: string, args: object) =>
  post<object>("/api/voice/tool", { conversation_id, name, args }).catch(() => ({ ok: false, error: "unavailable" }));

export const voiceTranscript = (conversation_id: string, turns: { role: "user" | "assistant"; text: string }[]) =>
  post<object>("/api/voice/transcript", { conversation_id, turns });
