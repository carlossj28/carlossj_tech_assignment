"use client";

import { useEffect, useRef } from "react";

export type Mood = "idle" | "listening" | "speaking" | "thinking";
type RGB = number[];

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const rand = (a: number, b: number) => a + Math.random() * (b - a);
const hex = (h: string): RGB => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const rgba = (c: RGB, a: number) => `rgba(${c.map(Math.round)},${a})`;

const SIZE = 420; // canvas units; CSS scales it
const C = SIZE / 2;
const R = 118;
const INK = "#120d2a";

// Aurora tokens (globals.css) per mood: violet at rest, cool while the candidate talks,
// warm while Rita talks, magenta swirl while she thinks. deep = body, mid = clouds, light = highlights.
const LOOK: Record<Mood, { deep: string; mid: string; light: string; glow: string; speed: number; deform: number; think: number }> = {
  idle: { deep: "#2b1f86", mid: "#8b7bff", light: "#f3eaff", glow: "#8b7bff", speed: 0.6, deform: 0.015, think: 0 },
  listening: { deep: "#3d6bff", mid: "#8b7bff", light: "#e6f4ff", glow: "#5cc8ff", speed: 1.1, deform: 0.03, think: 0 },
  speaking: { deep: "#6a2fd0", mid: "#ff7a66", light: "#ffd6be", glow: "#ff7a66", speed: 1.4, deform: 0.05, think: 0 },
  thinking: { deep: "#2b1f86", mid: "#e07bff", light: "#ffb86b", glow: "#e07bff", speed: 2.4, deform: 0.02, think: 1 },
};
const COLORS = ["deep", "mid", "light", "glow"] as const;

// Eyes: how much they smile (lower lid) and how the head tilts.
const FACE: Record<Mood, { happy: number; tilt: number }> = {
  idle: { happy: 0.45, tilt: 0 },
  listening: { happy: 0.25, tilt: 0.06 },
  speaking: { happy: 0.5, tilt: 0 },
  thinking: { happy: 0, tilt: -0.1 },
};

// Clouds of light drifting inside the orb.
const BLOBS = [
  { c: "mid", r: 0.95, fx: 0.7, fy: 0.9, o: 0, a: 0.9 },
  { c: "light", r: 0.6, fx: 1.1, fy: 0.6, o: 2, a: 0.7 },
  { c: "mid", r: 0.75, fx: 0.5, fy: 1.3, o: 4, a: 0.8 },
  { c: "light", r: 0.45, fx: 1.4, fy: 1, o: 1.3, a: 0.6 },
  { c: "deep", r: 0.7, fx: 0.9, fy: 0.4, o: 5, a: 0.9 },
] as const;

// Rita on a call: a living orb with glasses. `mood` sets colour, motion and expression;
// `level` (0–1) is the live loudness of whoever is talking, so the orb pulses with the real voice.
export default function VoiceOrb({ mood, level }: { mood: Mood; level: () => number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const props = useRef({ mood, level });
  useEffect(() => {
    props.current = { mood, level };
  });

  useEffect(() => {
    const ctx = canvas.current!.getContext("2d")!;
    const dpr = devicePixelRatio || 1;
    canvas.current!.width = canvas.current!.height = SIZE * dpr;
    ctx.scale(dpr, dpr);
    const calm = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0.3 : 1;

    const P = { speed: 0.6, deform: 0.015, think: 0, amp: 0, scale: 1, deep: [] as RGB, mid: [] as RGB, light: [] as RGB, glow: [] as RGB };
    COLORS.forEach((k) => (P[k] = hex(LOOK.idle[k])));
    const F = { ...FACE.idle, gx: 0, gy: 0 };
    let t = 0, ph = 0, spin = 0, last = performance.now(), frame = 0;
    let gaze = { x: 0, y: 0 }, sacT = 0, blinkIn = 2, blinkT = -1, joyT = 0;

    function shape(cx: number, cy: number, r: number, def: number) {
      ctx.beginPath();
      for (let i = 0; i <= 120; i++) {
        const a = (i / 120) * Math.PI * 2;
        const k = 1 + def * (Math.sin(3 * a + t * 1.3) * 0.5 + Math.sin(5 * a - t * 1.9 + 1) * 0.3 + Math.sin(2 * a + t * 0.8 + 2) * 0.4);
        ctx.lineTo(cx + Math.cos(a) * r * k, cy + Math.sin(a) * r * k);
      }
      ctx.closePath();
    }

    function eye(x: number, y: number, er: number, lid: number, happy: number) {
      ctx.save();
      // "Smiling" lower lid: a circle cuts away the bottom of the eye.
      ctx.beginPath();
      ctx.rect(x - er * 2, y - er * 2, er * 4, er * 4);
      ctx.arc(x, y + er * (2.15 - happy * 1.35), er * 1.3, 0, Math.PI * 2);
      ctx.clip("evenodd");
      ctx.beginPath();
      ctx.ellipse(x, y, er, er * 1.08 * lid, 0, 0, Math.PI * 2);
      ctx.clip();
      ctx.fillStyle = "#fbfcff";
      ctx.fillRect(x - er, y - er * 1.2, er * 2, er * 2.4);
      const ix = x + F.gx * er * 0.38, iy = y + F.gy * er * 0.3, ir = er * 0.6;
      const iris = ctx.createRadialGradient(ix, iy - ir * 0.3, 0, ix, iy, ir);
      iris.addColorStop(0, rgba(P.mid.map((v) => v * 0.55), 1));
      iris.addColorStop(0.7, "#140d33");
      iris.addColorStop(1, "#0b0720");
      ctx.fillStyle = iris;
      ctx.beginPath();
      ctx.arc(ix, iy, ir, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#05030f";
      ctx.beginPath();
      ctx.arc(ix, iy, ir * 0.48, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.arc(ix + ir * 0.35, iy - ir * 0.38, ir * 0.3, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(ix - ir * 0.35, iy + ir * 0.35, ir * 0.13, 0, Math.PI * 2);
      ctx.fill();
      const lidShade = ctx.createLinearGradient(0, y - er, 0, y - er * 0.3);
      lidShade.addColorStop(0, "rgba(20,15,60,.35)");
      lidShade.addColorStop(1, "rgba(20,15,60,0)");
      ctx.fillStyle = lidShade;
      ctx.fillRect(x - er, y - er * 1.2, er * 2, er);
      ctx.restore();
    }

    function face(cx: number, cy: number, r: number, dt: number, mood: Mood) {
      F.happy = lerp(F.happy, FACE[mood].happy, 0.1);
      F.tilt = lerp(F.tilt, FACE[mood].tilt, 0.1);

      // Gaze: wanders at rest, looks up and away while thinking, at you otherwise.
      if ((sacT -= dt) <= 0) {
        sacT = rand(0.9, 2.8);
        gaze = mood === "thinking" ? { x: rand(0.6, 0.9), y: rand(-0.9, -0.7) }
             : mood === "idle" ? { x: rand(-0.6, 0.6), y: rand(-0.3, 0.3) }
             : { x: rand(-0.15, 0.15), y: rand(-0.1, 0.1) };
      }
      F.gx = lerp(F.gx, gaze.x, 0.2);
      F.gy = lerp(F.gy, gaze.y, 0.2);

      // Blinks, sometimes twice.
      if ((blinkIn -= dt) <= 0) {
        blinkT = 0;
        blinkIn = Math.random() < 0.2 ? 0.25 : rand(2.2, 5);
      }
      let lid = 1;
      if (blinkT >= 0) {
        blinkT += dt;
        if (blinkT < 0.16) lid = 1 - 0.92 * Math.sin((blinkT / 0.16) * Math.PI);
        else blinkT = -1;
      }

      // At rest she now and then smiles with her eyes (^ ^).
      if (mood === "idle" && (joyT -= dt) <= 0) joyT = rand(4, 8);
      const joy = mood === "idle" && joyT < 1.1 ? Math.sin((joyT / 1.1) * Math.PI) : 0;
      const happy = Math.min(1, F.happy + joy * 0.6 + (mood === "speaking" ? P.amp * 0.25 : 0));

      const nod = mood === "listening" ? ((Math.sin(t * 2.4) * 0.5 + 0.5) ** 6) * r * 0.04 : 0;
      ctx.save();
      ctx.translate(cx + F.gx * r * 0.07, cy - r * 0.02 + F.gy * r * 0.05 + nod);
      ctx.rotate(F.tilt + Math.sin(t * 0.8) * 0.02);
      const ex = r * 0.31, er = r * 0.19, gr = r * 0.27;
      eye(-ex, 0, er, lid, happy);
      eye(ex, 0, er, lid, happy);

      // Glasses: lenses, a glint, temples and the bridge.
      ctx.lineCap = "round";
      for (const s of [-1, 1]) {
        ctx.fillStyle = "rgba(200,225,255,.07)";
        ctx.beginPath();
        ctx.arc(s * ex, 0, gr, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = INK;
        ctx.lineWidth = r * 0.045;
        ctx.stroke();
        ctx.strokeStyle = "rgba(255,255,255,.5)";
        ctx.lineWidth = r * 0.018;
        ctx.beginPath();
        ctx.arc(s * ex, 0, gr * 0.78, Math.PI * 1.1, Math.PI * 1.38);
        ctx.stroke();
        ctx.strokeStyle = INK;
        ctx.lineWidth = r * 0.04;
        ctx.beginPath();
        ctx.moveTo(s * (ex + gr), -gr * 0.15);
        ctx.lineTo(s * (ex + gr + r * 0.12), -gr * 0.3);
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.moveTo(-ex + gr, -gr * 0.05);
      ctx.quadraticCurveTo(0, -gr * 0.45, ex - gr, -gr * 0.05);
      ctx.stroke();
      ctx.restore();
    }

    function draw(now: number) {
      const { mood, level } = props.current;
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      t += dt * calm;
      const look = LOOK[mood];
      P.speed = lerp(P.speed, look.speed, 0.05);
      P.deform = lerp(P.deform, look.deform, 0.05);
      P.think = lerp(P.think, look.think, 0.05);
      COLORS.forEach((k) => {
        const target = hex(look[k]);
        P[k] = P[k].map((v, i) => lerp(v, target[i], 0.05));
      });
      P.amp = lerp(P.amp, mood === "speaking" || mood === "listening" ? level() : 0, 0.18);

      ph += dt * P.speed * calm;
      spin += dt * (0.4 + P.think * 2.2) * calm;
      const target = mood === "speaking" ? 1 + P.amp * 0.14
                   : mood === "listening" ? 1 + P.amp * 0.08
                   : mood === "thinking" ? 0.94 + Math.sin(t * 2.2) * 0.025
                   : 1 + Math.sin(t * 1.4) * 0.015;
      P.scale = lerp(P.scale, target, 0.15);

      const float = Math.sin(t * 1.1) * 8, cx = C, cy = C - 10 + float, r = R * P.scale;
      const def = P.deform + P.amp * 0.06;
      ctx.clearRect(0, 0, SIZE, SIZE);

      // Shadow on the "floor": smaller when the orb rises.
      const floor = C + R + 52;
      const shadow = ctx.createRadialGradient(C, floor, 0, C, floor, R);
      shadow.addColorStop(0, rgba(P.glow, 0.28 - float * 0.012));
      shadow.addColorStop(1, rgba(P.glow, 0));
      ctx.save();
      ctx.translate(C, floor);
      ctx.scale(1 - float * 0.01, 0.16);
      ctx.translate(-C, -floor);
      ctx.fillStyle = shadow;
      ctx.fillRect(0, 0, SIZE, SIZE);
      ctx.restore();

      // Halo
      ctx.save();
      ctx.shadowColor = rgba(P.glow, 0.55 + P.amp * 0.35);
      ctx.shadowBlur = 50 + P.amp * 40;
      shape(cx, cy, r, def);
      ctx.fillStyle = rgba(P.deep, 1);
      ctx.fill();
      ctx.restore();

      // Body: base gradient, drifting clouds, and a swirl of light while thinking.
      ctx.save();
      shape(cx, cy, r, def);
      ctx.clip();
      const base = ctx.createRadialGradient(cx, cy + r * 0.3, 0, cx, cy, r * 1.1);
      base.addColorStop(0, rgba(P.mid, 1));
      base.addColorStop(1, rgba(P.deep, 1));
      ctx.fillStyle = base;
      ctx.fillRect(0, 0, SIZE, SIZE);

      ctx.globalCompositeOperation = "screen";
      for (const b of BLOBS) {
        const bx = cx + Math.cos(ph * b.fx + b.o) * r * 0.5, by = cy + Math.sin(ph * b.fy + b.o * 1.7) * r * 0.45;
        const cloud = ctx.createRadialGradient(bx, by, 0, bx, by, r * b.r * (1 + P.amp * 0.2));
        cloud.addColorStop(0, rgba(P[b.c], b.a));
        cloud.addColorStop(1, rgba(P[b.c], 0));
        ctx.fillStyle = cloud;
        ctx.fillRect(0, 0, SIZE, SIZE);
      }
      if (P.think > 0.01) {
        const swirl = ctx.createConicGradient(spin, cx, cy);
        swirl.addColorStop(0, rgba(P.light, 0));
        swirl.addColorStop(0.15, rgba(P.light, 0.55 * P.think));
        swirl.addColorStop(0.35, rgba(P.light, 0));
        swirl.addColorStop(0.6, rgba(P.mid, 0.4 * P.think));
        swirl.addColorStop(0.8, rgba(P.light, 0));
        swirl.addColorStop(1, rgba(P.light, 0));
        ctx.fillStyle = swirl;
        ctx.fillRect(0, 0, SIZE, SIZE);
      }

      // Volume: darker rim, the face, then a highlight on top.
      ctx.globalCompositeOperation = "source-over";
      const edge = ctx.createRadialGradient(cx, cy, r * 0.55, cx, cy, r * 1.05);
      edge.addColorStop(0, "rgba(5,8,30,0)");
      edge.addColorStop(1, "rgba(5,8,30,.45)");
      ctx.fillStyle = edge;
      ctx.fillRect(0, 0, SIZE, SIZE);
      face(cx, cy, r, dt, mood);
      const shine = ctx.createRadialGradient(cx - r * 0.5, cy - r * 0.62, 0, cx - r * 0.5, cy - r * 0.62, r * 0.45);
      shine.addColorStop(0, "rgba(255,255,255,.4)");
      shine.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = shine;
      ctx.fillRect(0, 0, SIZE, SIZE);
      ctx.restore();

      shape(cx, cy, r, def);
      ctx.strokeStyle = "rgba(255,255,255,.18)";
      ctx.lineWidth = 1.2;
      ctx.stroke();

      frame = requestAnimationFrame(draw);
    }
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, []);

  return <canvas ref={canvas} role="img" aria-label="Rita, asistente de voz" style={{ width: "100%", aspectRatio: "1" }} />;
}
