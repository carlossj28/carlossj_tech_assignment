import { expect, test, type Page } from "@playwright/test";

// A fake call: mic, WebRTC and OpenAI are stubbed, and the test plays Realtime events with `rt`.
async function fakeCall(page: Page, { mic = true } = {}) {
  await page.addInitScript((mic) => {
    const w = window as unknown as Record<string, unknown>;
    navigator.mediaDevices.getUserMedia = async () => {
      if (!mic) throw new DOMException("denied", "NotAllowedError");
      return new AudioContext().createMediaStreamDestination().stream; // a real, silent audio track
    };
    w.RTCPeerConnection = class {
      addTrack() {}
      createDataChannel() {
        const channel = { send() {}, onopen: () => {}, onmessage: (_: object) => {} };
        w.channel = channel;
        setTimeout(() => channel.onopen());
        return channel;
      }
      async createOffer() {
        return { type: "offer", sdp: "v=0" };
      }
      async setLocalDescription() {}
      async setRemoteDescription() {}
      getSenders() {
        return [];
      }
      close() {}
    };
  }, mic);
  await page.route("**/api/voice/session", (r) => r.fulfill({ json: { conversation_id: "v1", client_secret: "s" } }));
  await page.route("**/api/voice/transcript", (r) => r.fulfill({ json: {} }));
  await page.route("**/api/voice/tool", (r) => r.fulfill({ json: { ok: true } }));
  await page.route("https://api.openai.com/**", (r) => r.fulfill({ body: "v=0" }));
}

const rt = (page: Page, event: object) =>
  page.evaluate((e) => (window as unknown as { channel: { onmessage: (m: object) => void } }).channel.onmessage({ data: JSON.stringify(e) }), event);

const status = (page: Page) => page.locator('[aria-label="Llamada con Rita"] .eyebrow');

async function startCall(page: Page) {
  await page.goto("/voz");
  await page.getByRole("button", { name: "Llamar" }).click();
  await expect(page.getByRole("button", { name: "Colgar" })).toBeVisible();
}

test("the chat offers the voice call next to the composer", async ({ page }) => {
  await page.route("**/api/chat/start", (r) => r.fulfill({ json: { conversation_id: "c1", greeting: "¡Hola!" } }));
  await page.goto("/");
  await page.getByRole("link", { name: "Llamar a Rita" }).click();
  await expect(page).toHaveURL(/\/voz$/);
  await expect(page.getByRole("button", { name: "Llamar" })).toBeVisible();
});

test("Rita's mood follows the call and the last lines show as subtitles", async ({ page }) => {
  await fakeCall(page);
  await startCall(page);

  await rt(page, { type: "output_audio_buffer.started" });
  await expect(status(page)).toHaveText("Hablando…");
  await rt(page, { type: "response.output_audio_transcript.done", transcript: "¡Hola! ¿Cómo te llamas?" });
  await expect(page.locator('[data-role="rita"]')).toHaveText("¡Hola! ¿Cómo te llamas?");

  await rt(page, { type: "output_audio_buffer.stopped" });
  await expect(status(page)).toHaveText("Te escucho…");
  await rt(page, { type: "input_audio_buffer.speech_started" });
  await rt(page, { type: "input_audio_buffer.speech_stopped" });
  await expect(status(page)).toHaveText("Pensando…");
  await rt(page, { type: "conversation.item.input_audio_transcription.completed", transcript: "Ana López" });
  await expect(page.getByText("Tú: «Ana López»")).toBeVisible();

  await page.getByRole("button", { name: "Colgar" }).click();
  await expect(status(page)).toHaveText("Llamada terminada");
  await expect(page.getByRole("button", { name: "Llamar de nuevo" })).toBeVisible();
});

test("the full transcript is one tap away", async ({ page }) => {
  await fakeCall(page);
  await startCall(page);
  await rt(page, { type: "response.output_audio_transcript.done", transcript: "¿Cómo te llamas?" });
  await rt(page, { type: "conversation.item.input_audio_transcription.completed", transcript: "Ana" });

  await page.getByRole("button", { name: "Ver conversación completa" }).click();
  await expect(page.locator('[data-role="rita"]')).toHaveText("¿Cómo te llamas?");
  await expect(page.locator('[data-role="candidate"]')).toHaveText("Ana");
  await page.getByRole("button", { name: "Volver a Rita" }).click();
  await expect(page.getByText("Tú: «Ana»")).toBeVisible();
});

test("after end_interview, Rita's goodbye ends the call for good", async ({ page }) => {
  await fakeCall(page);
  await startCall(page);
  await expect(page.getByRole("link", { name: "Prefiero escribir" })).toBeVisible(); // mid-call: switching is fine
  const stored = page.waitForResponse("**/api/voice/tool"); // the back closes the interview first
  await rt(page, { type: "response.function_call_arguments.done", name: "end_interview", call_id: "1", arguments: "{}" });
  await expect(status(page)).toHaveText("Pensando…");
  await stored;
  await rt(page, { type: "response.done", response: { output: [{ type: "message" }] } });
  await rt(page, { type: "output_audio_buffer.stopped" });

  await expect(page.getByText("Entrevista terminada").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Llamar|Colgar/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Prefiero escribir" })).toHaveCount(0); // no second interview by chat
});

test("a denied microphone shows an error and lets the candidate try again", async ({ page }) => {
  await fakeCall(page, { mic: false });
  await page.goto("/voz");
  await page.getByRole("button", { name: "Llamar" }).click();
  await expect(page.getByText("Revisa el permiso del micrófono")).toBeVisible();
  await expect(page.getByRole("button", { name: "Llamar" })).toBeEnabled();
});
