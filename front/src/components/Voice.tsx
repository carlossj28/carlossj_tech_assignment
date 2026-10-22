"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import * as api from "@/lib/api";
import Aurora from "./Aurora";
import Brand from "./Brand";
import MessageList, { type Message } from "./MessageList";
import Orb from "./Orb";
import styles from "./chat.module.css";

type State = "idle" | "connecting" | "live" | "ended";
type Turn = { role: "user" | "assistant"; text: string };

// Voice call with Rita: audio goes browser ↔ OpenAI (WebRTC); we relay to the back only
// what must be stored — tool calls and finished sentences. Same brain as the chat.
export default function Voice() {
  const [state, setState] = useState<State>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pc = useRef<RTCPeerConnection | null>(null);
  const cid = useRef("");
  const pending = useRef<Turn[]>([]); // Rita's sentences before the candidate speaks (not stored alone)
  const queue = useRef(Promise.resolve()); // back calls one at a time: no 409 between tool and transcript

  const relay = (job: () => Promise<unknown>) => (queue.current = queue.current.then(job).then(() => undefined, () => undefined));

  // A finished sentence: show it, and store it once the candidate has spoken (decision 1a).
  function sentence(turn: Turn) {
    setMessages((m) => [...m, { role: turn.role === "user" ? "candidate" : "rita", text: turn.text }]);
    pending.current.push(turn);
    if (!pending.current.some((t) => t.role === "user")) return;
    const turns = pending.current;
    pending.current = [];
    relay(() => api.voiceTranscript(cid.current, turns));
  }

  async function call() {
    setError(null);
    setMessages([]);
    setState("connecting");
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      const { conversation_id, client_secret } = await api.voiceSession();
      cid.current = conversation_id;

      const conn = new RTCPeerConnection();
      pc.current = conn;
      const speaker = new Audio();
      speaker.autoplay = true;
      conn.ontrack = (e) => (speaker.srcObject = e.streams[0]);
      conn.addTrack(mic.getTracks()[0]);

      const events = conn.createDataChannel("oai-events");
      const send = (event: object) => events.send(JSON.stringify(event));
      events.onopen = () => {
        setState("live");
        send({ type: "response.create" }); // Rita speaks first: greets and asks the name
      };
      events.onmessage = (e) => {
        const ev = JSON.parse(e.data);
        if (ev.type === "conversation.item.input_audio_transcription.completed" && ev.transcript?.trim())
          sentence({ role: "user", text: ev.transcript.trim() });
        else if (ev.type === "response.output_audio_transcript.done" && ev.transcript?.trim())
          sentence({ role: "assistant", text: ev.transcript.trim() });
        else if (ev.type === "response.function_call_arguments.done")
          relay(async () => {
            const out = await api.voiceTool(cid.current, ev.name, JSON.parse(ev.arguments || "{}"));
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
    pc.current?.getSenders().forEach((s) => s.track?.stop());
    pc.current?.close();
    pc.current = null;
    setState((s) => (s === "live" ? "ended" : s));
  }

  useEffect(() => hangUp, []); // leaving the page ends the call

  const live = state === "live";
  return (
    <main className={styles.page}>
      <Aurora />
      <header className={styles.bar}>
        <Brand area="Repartidores" />
        <Link className={styles.staff} href="/">Prefiero escribir</Link>
      </header>

      <div className={styles.layout}>
        <section className={styles.hero}>
          <h1 className={styles.title}>
            Habla con <span className={styles.glow}>Rita</span>
          </h1>
          <p className={styles.lead}>Una llamada corta sobre tu candidatura. Necesitas micrófono.</p>
        </section>

        <section className={styles.card} aria-label="Llamada con Rita">
          <div className={styles.agent}>
            <Orb size={44} active={live} />
            <span className={styles.who}>
              <strong>Rita</strong>
              <span>Asistente de selección</span>
            </span>
            <span className={`${styles.presence} eyebrow ${live ? styles.busy : ""}`}>
              {{ idle: "Lista", connecting: "Conectando…", live: "En llamada", ended: "Llamada terminada" }[state]}
            </span>
          </div>

          <MessageList messages={messages} />
          {error && <p className={styles.error} role="alert">{error}</p>}
          <button className={styles.send} style={{ alignSelf: "center", margin: "12px 0 0" }}
                  onClick={live ? hangUp : call} disabled={state === "connecting"}>
            {live ? "Colgar" : state === "ended" ? "Llamar de nuevo" : "Llamar"}
          </button>
          <p className={styles.disclaimer}>Rita es una IA · La llamada se transcribe para el equipo de selección.</p>
        </section>
      </div>
    </main>
  );
}
