import { expect, test, type Page } from "@playwright/test";

const GREETING = "¡Hola! Soy Rita, de Grupo Sazón.";

// Mock the three chat endpoints. `message` decides each reply; nudge replies `nudges` times, then null.
async function mockBack(page: Page, { message, nudges = 0 }: { message?: (text: string) => object | undefined; nudges?: number } = {}) {
  const calls = { nudge: 0 };
  await page.route("**/api/chat/start", (r) => r.fulfill({ json: { conversation_id: "c1", greeting: GREETING } }));
  await page.route("**/api/chat/message", (r) => {
    const { message: text } = r.request().postDataJSON();
    const body = message?.(text);
    return body ? r.fulfill({ json: body }) : r.fulfill({ status: 500, json: { detail: "boom" } });
  });
  await page.route("**/api/chat/nudge", (r) => {
    calls.nudge++;
    return r.fulfill({ json: { reply: calls.nudge <= nudges ? `¿Sigues ahí? (${calls.nudge})` : null } });
  });
  return calls;
}

const send = async (page: Page, text: string) => {
  await page.getByLabel("Tu respuesta").fill(text);
  await page.getByRole("button", { name: "Enviar" }).click();
};

test("shows Rita's greeting on load", async ({ page }) => {
  await mockBack(page);
  await page.goto("/");
  await expect(page.locator('[data-role="rita"]')).toHaveText(GREETING);
});

test("a sent message gets Rita's reply", async ({ page }) => {
  await mockBack(page, { message: (t) => ({ reply: `Encantada, ${t}`, completed: false, status: "pending" }) });
  await page.goto("/");
  await send(page, "Ana López");
  await expect(page.locator('[data-role="candidate"]')).toHaveText("Ana López");
  await expect(page.locator('[data-role="rita"]').last()).toHaveText("Encantada, Ana López");
});

test("a failed send shows an error and keeps the text to retry", async ({ page }) => {
  let fail = true;
  await mockBack(page, { message: () => (fail ? undefined : { reply: "Gracias", completed: false, status: "pending" }) });
  await page.goto("/");
  await send(page, "Ana");
  await expect(page.getByText("problema técnico")).toBeVisible();
  await expect(page.locator('[data-role="candidate"]')).toHaveCount(0);
  await expect(page.getByLabel("Tu respuesta")).toHaveValue("Ana");

  fail = false;
  await page.getByRole("button", { name: "Enviar" }).click();
  await expect(page.locator('[data-role="rita"]').last()).toHaveText("Gracias");
  await expect(page.getByText("problema técnico")).toHaveCount(0);
});

test("a failed start can be retried", async ({ page }) => {
  let fail = true;
  await page.route("**/api/chat/start", (r) =>
    fail ? r.fulfill({ status: 503, json: { detail: "down" } }) : r.fulfill({ json: { conversation_id: "c1", greeting: GREETING } }),
  );
  await page.goto("/");
  await expect(page.getByText("No hemos podido iniciar")).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.locator('[data-role="rita"]')).toHaveText(GREETING);
});

test("silence triggers reminders, and stops when the back says no more", async ({ page }) => {
  await page.clock.install();
  const calls = await mockBack(page, { nudges: 3, message: () => ({ reply: "¿Tienes carné?", completed: false, status: "pending" }) });
  await page.goto("/");
  await expect(page.locator('[data-role="rita"]')).toHaveText(GREETING);

  await page.clock.runFor(60_000); // no reminders before the candidate's first message
  expect(calls.nudge).toBe(0);

  await send(page, "Hola");
  await expect(page.locator('[data-role="rita"]').last()).toHaveText("¿Tienes carné?");
  for (let i = 1; i <= 3; i++) {
    await page.clock.runFor(60_000);
    await expect(page.locator('[data-role="rita"]').last()).toHaveText(`¿Sigues ahí? (${i})`);
  }
  await page.clock.runFor(60_000); // 4th call → null
  await expect.poll(() => calls.nudge).toBe(4);
  await page.clock.runFor(5 * 60_000);
  expect(calls.nudge).toBe(4);
  await expect(page.locator('[data-role="rita"]')).toHaveCount(5);
});

test("a completed interview shows the tag and a new message reopens it", async ({ page }) => {
  let completed = true;
  await mockBack(page, { message: () => ({ reply: "Respuesta", completed, status: "qualified" }) });
  await page.goto("/");
  await send(page, "Sí, confirmo");
  await expect(page.getByText("Entrevista completada")).toBeVisible();
  await expect(page.getByLabel("Tu respuesta")).toBeEnabled();

  completed = false;
  await send(page, "Perdona, vivo en Madrid");
  await expect(page.locator('[data-role="rita"]')).toHaveCount(3);
  await expect(page.getByText("Entrevista completada")).toHaveCount(0);
});
