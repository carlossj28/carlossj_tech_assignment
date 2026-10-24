"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import * as api from "@/lib/api";
import Aurora from "./Aurora";
import Booking from "./Booking";
import Brand from "./Brand";
import MessageList, { type Message } from "./MessageList";
import PhoneIcon from "./PhoneIcon";
import VoiceOrb, { type Mood } from "./VoiceOrb";
import styles from "./chat.module.css";
import voice from "./voice.module.css";

type State = "idle" | "connecting" | "live" | "ended" | "done"; // done: Rita closed the interview
type Turn = { role: "user" | "assistant"; text: string };

// Realtime events that change Rita's mood on screen.
const MOOD: Record<string, Mood> = {
  "input_audio_buffer.speech_started": "listening",
  "input_audio_buffer.speech_stopped": "thinking",
  "response.function_call_arguments.done": "thinking",
  "output_audio_buffer.started": "speaking",
  "output_audio_buffer.stopped": "listening",
};
const MOOD_LABEL: Record<Mood, string> = { idle: "En línea", listening: "Te escucho…", speaking: "Hablando…", thinking: "Pensando…" };

// Live loudness (0–1) of an audio stream, so the orb moves with the real voice.
function meter(audio: AudioContext, stream: MediaStream) {
  const analyser = audio.createAnalyser();
  audio.createMediaStreamSource(stream).connect(analyser);
  const wave = new Uint8Array(analyser.fftSize);
  return () => {
    analyser.getByteTimeDomainData(wave);
    let peak = 0;
    for (const v of wave) peak = Math.max(peak, Math.abs(v - 128));
    return Math.min(1, peak / 64);
  };
}

// Voice call with Rita: audio goes browser ↔ OpenAI (WebRTC); we relay to the back only
// what must be stored — tool calls and finished sentences. Same brain as the chat.
export default function Voice() {
  const [state, setState] = useState<State>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [mood, setMood] = useState<Mood>("idle");
  const [showAll, setShowAll] = useState(false); // full transcript instead of subtitles
  const [qualified, setQualified] = useState(false); // from each tool result's status
  const [interviewAt, setInterviewAt] = useState<string | null>(null);
  const audio = useRef<AudioContext | null>(null);
  const meters = useRef<Partial<Record<Mood, () => number>>>({}); // candidate's mic while listening, Rita while speaking
  const pc = useRef<RTCPeerConnection | null>(null);
  const cid = useRef("");
  // The call's sentences in the order they were said. The candidate's line takes its place when they
  // stop speaking and gets its text when the transcript arrives, often after Rita has answered.
  const lines = useRef<{ id?: string; turn?: Turn; waiting: boolean }[]>([]);
  const stored = useRef(0); // lines already sent to the back
  const queue = useRef(Promise.resolve()); // back calls one at a time: no 409 between tool and transcript
  // Hang-up after end_interview (ADR-029): "closing" once it succeeded, "bye" once the goodbye
  // that follows it is generated; the call ends when that audio stops playing.
  const ending = useRef<"no" | "closing" | "bye">("no");
  const fallback = useRef<ReturnType<typeof setTimeout>>(undefined);

  const relay = (job: () => Promise<unknown>) => (queue.current = queue.current.then(job).then(() => undefined, () => undefined));

  // The lines before the first one still waiting for its transcript: show them, and store the new
  // ones once the candidate has spoken (decision 1a: a call nobody answers stores nothing).
  function publish() {
    const end = lines.current.findIndex((l) => l.waiting);
    const ready = lines.current.slice(0, end < 0 ? undefined : end);
    const said = (from: number) => ready.slice(from).flatMap((l) => (l.turn ? [l.turn] : []));
    setMessages(said(0).map((t) => ({ role: t.role === "user" ? "candidate" : "rita", text: t.text })));
    if (!said(0).some((t) => t.role === "user")) return;
    const turns = said(stored.current);
    stored.current = ready.length;
    if (turns.length) relay(() => api.voiceTranscript(cid.current, turns));
  }

  // The candidate's transcript (empty if it failed) fills the place they took when they stopped speaking.
  function heard(id: string | undefined, text: string) {
    let line = lines.current.find((l) => l.waiting && l.id === id);
    if (!line) lines.current.push((line = { id, waiting: true }));
    line.waiting = false;
    if (text) line.turn = { role: "user", text };
    publish();
  }

  async function call() {
    setError(null);
    setMessages([]);
    lines.current = [];
    stored.current = 0;
    setState("connecting");
    setMood("thinking");
    ending.current = "no";
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      const { conversation_id, client_secret } = await api.voiceSession();
      cid.current = conversation_id;
      audio.current = new AudioContext();
      meters.current = { listening: meter(audio.current, mic) };

      const conn = new RTCPeerConnection();
      pc.current = conn;
      const speaker = new Audio();
      speaker.autoplay = true;
      conn.ontrack = (e) => {
        speaker.srcObject = e.streams[0];
        meters.current.speaking = meter(audio.current!, e.streams[0]);
      };
      conn.addTrack(mic.getTracks()[0]);

      const events = conn.createDataChannel("oai-events");
      const send = (event: object) => events.send(JSON.stringify(event));
      events.onopen = () => {
        setState("live");
        send({ type: "response.create" }); // Rita speaks first: greets and asks the name
      };
      events.onmessage = (e) => {
        const ev = JSON.parse(e.data);
        if (MOOD[ev.type]) setMood(MOOD[ev.type]);
        if (ev.type === "input_audio_buffer.committed") lines.current.push({ id: ev.item_id, waiting: true });
        else if (ev.type === "conversation.item.input_audio_transcription.completed"
                 || ev.type === "conversation.item.input_audio_transcription.failed")
          heard(ev.item_id, ev.transcript?.trim() ?? "");
        else if (ev.type === "response.output_audio_transcript.done" && ev.transcript?.trim()) {
          lines.current.push({ turn: { role: "assistant", text: ev.transcript.trim() }, waiting: false });
          publish();
        }
        else if (ev.type === "response.done" && ending.current === "closing"
                 && !ev.response?.output?.some((item: { type: string }) => item.type === "function_call"))
          ending.current = "bye";
        else if (ev.type === "output_audio_buffer.stopped" && ending.current === "bye")
          finish();
        else if (ev.type === "response.function_call_arguments.done")
          relay(async () => {
            const out = await api.voiceTool(cid.current, ev.name, JSON.parse(ev.arguments || "{}"));
            if (out.status) setQualified(out.status === "qualified");
            if (ev.name === "book_interview" && out.interview_at) setInterviewAt(out.interview_at);
            if (ev.name === "end_interview" && out.ok) {
              ending.current = "closing";
              fallback.current = setTimeout(finish, 15000); // in case the audio-stopped event never comes
            }
            send({ type: "conversation.item.create", item: { type: "function_call_output", call_id: ev.call_id, output: JSON.stringify(out) } });
            send({ type: "response.create" }); // let Rita react to the result
          });
      };

      const offer = await conn.createOffer();
      await conn.setLocalDescription(offer);
      const answer = await fetch("https://api.openai.com/v1/realtime/calls", {
        method: "POST",
        body: offer.sdp,
        headers: { Authorization: `Bearer ${client_secret}`, "Content-Type": "application/sdp" },
      });
      if (!answer.ok) throw new Error(`realtime → ${answer.status}`);
      await conn.setRemoteDescription({ type: "answer", sdp: await answer.text() });
    } catch {
      hangUp();
      setError("No hemos podido iniciar la llamada. Revisa el permiso del micrófono e inténtalo de nuevo.");
      setState("idle");
    }
  }

  // UI only: stops the mic and the link to OpenAI. What was stored stays; an unfinished
  // interview shows as inactive in the panel after 5 minutes.
  function hangUp() {
    clearTimeout(fallback.current);
    pc.current?.getSenders().forEach((s) => s.track?.stop());
    pc.current?.close();
    pc.current = null;
    audio.current?.close();
    audio.current = null;
    setMood("idle");
    setState((s) => (s === "live" ? "ended" : s));
  }

  // Rita closed the interview: the call ends for good, no "call again" (ADR-029).
  function finish() {
    hangUp();
    setState("done");
  }

  useEffect(() => hangUp, []); // leaving the page ends the call

  const live = state === "live";
  const lastRita = messages.findLast((m) => m.role === "rita")?.text;
  const lastYou = messages.findLast((m) => m.role === "candidate")?.text;
  return (
    <main className={styles.page}>
      <Aurora />
      <header className={styles.bar}>
        <Brand area="Repartidores" />
        {/* Back to the text chat; on a phone it shrinks to an icon, like the chat's recruiter link.
            Hidden once the interview is done: the chat would start a second one for the same candidate. */}
        {state !== "done" && (
          <Link className={styles.staff} href="/" aria-label="Prefiero escribir">
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden>
              <path d="M4.5 11.5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H7.5l-3 2.5Z" />
            </svg>
            <span className={styles.staffText}>Prefiero escribir</span>
          </Link>
        )}
      </header>

      <div className={styles.layout}>
        <section className={styles.hero}>
          <h1 className={styles.title}>
            Habla con <span className={styles.glow}>Rita</span>
          </h1>
          <p className={styles.lead}>Una llamada corta sobre tu candidatura. Necesitas micrófono.</p>
        </section>

        <section className={`${styles.card} ${voice.card}`} aria-label="Llamada con Rita">
          <div className={`${voice.stage} ${showAll ? voice.compact : ""}`}>
            <div className={voice.orb}>
              <VoiceOrb mood={mood} level={() => meters.current[mood]?.() ?? 0} />
            </div>
            <p className={`${voice.status} ${live ? voice.on : ""} eyebrow`}>
              {live ? MOOD_LABEL[mood] : { idle: "Rita · Asistente de selección", connecting: "Conectando…", ended: "Llamada terminada", done: "Llamada finalizada" }[state]}
            </p>
          </div>

          {/* During the call only the last lines show, like subtitles; the full transcript is one tap away. */}
          {showAll ? (
            <MessageList messages={messages} />
          ) : (
            <div className={voice.subtitles} aria-live="polite">
              <p className={voice.said} data-role="rita">{lastRita ?? "Pulsa Llamar y Rita te saludará."}</p>
              {lastYou && <p className={voice.you}>Tú: «{lastYou}»</p>}
            </div>
          )}

          {error && <p className={styles.error} role="alert">{error}</p>}
          {state === "done" ? (
            <p className={styles.done}>
              <svg className={styles.check} viewBox="0 0 32 32" aria-hidden>
                <circle cx="16" cy="16" r="15" />
                <path d="m10 16.5 4 4 8-9" pathLength={1} />
              </svg>
              <span>
                <strong>Entrevista terminada</strong> Gracias, el equipo de selección revisará tu candidatura.
              </span>
            </p>
          ) : (
            <button className={`${styles.send} ${voice.call} ${live ? voice.hangUp : ""}`} onClick={live ? hangUp : call} disabled={state === "connecting"}>
              <PhoneIcon />
              {live ? "Colgar" : state === "ended" ? "Llamar de nuevo" : "Llamar"}
            </button>
          )}
          {qualified && (interviewAt || state === "done") && <Booking interviewAt={interviewAt} uid={cid.current} />}
          {messages.length > 0 && (
            <button className={voice.toggle} onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Volver a Rita" : "Ver conversación completa"}
            </button>
          )}
          <p className={`${styles.disclaimer} ${voice.foot}`}>Rita es una IA · La llamada se transcribe para el equipo de selección.</p>
        </section>
      </div>
    </main>
  );
}
