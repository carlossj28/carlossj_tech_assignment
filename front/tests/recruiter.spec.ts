import { expect, test, type Page } from "@playwright/test";

const ROWS = [
  { id: "a", candidate_name: "Marta Gil", city: "Madrid", source: "chat", screening_status: "qualified", knockout_reason: null,
    completed: true, inactive: false, created_at: "2026-10-21T10:00:00Z", last_activity_at: "2026-10-21T10:05:00Z" },
  { id: "b", candidate_name: "Jorge Ruiz", city: "Madrid", source: "chat", screening_status: "disqualified", knockout_reason: "no_license",
    completed: true, inactive: false, created_at: "2026-10-21T09:00:00Z", last_activity_at: "2026-10-21T09:02:00Z" },
  { id: "c", candidate_name: null, city: "Sevilla", source: "voice", screening_status: "pending", knockout_reason: null,
    completed: false, inactive: true, created_at: "2026-10-21T08:00:00Z", last_activity_at: "2026-10-21T08:01:00Z" },
];

const DETAIL = {
  ...ROWS[0],
  extracted_fields: { full_name: "Marta Gil", has_driver_license: true, city: "Madrid", availability: ["full_time"],
    prior_experience: { years: 2, platforms: ["Glovo"] } },
  summary: "Repartidora con 2 años en Glovo; Madrid; jornada completa.",
  turns: [
    { role: "assistant", content: "¿Tienes carné?", created_at: "2026-10-21T10:00:00Z" },
    { role: "user", content: "Sí, desde 2019", created_at: "2026-10-21T10:01:00Z" },
  ],
};

// Mock the recruiter API. `loggedIn` flips on a successful login (password "ok") and off on logout.
async function mockBack(page: Page, { loggedIn = true } = {}) {
  let session = loggedIn;
  const guard = (body: object) => (session ? { json: body } : { status: 401, json: { detail: "not logged in" } });
  await page.route("**/api/recruiter/login", (r) => {
    session = r.request().postDataJSON().password === "ok";
    return r.fulfill(session ? { json: { username: "demo" } } : { status: 401, json: { detail: "invalid credentials" } });
  });
  await page.route("**/api/recruiter/logout", (r) => {
    session = false;
    return r.fulfill({ json: { ok: true } });
  });
  await page.route("**/api/recruiter/conversations", (r) => r.fulfill(guard(ROWS)));
  await page.route("**/api/recruiter/conversations/a", (r) => r.fulfill(guard(DETAIL)));
}

const rows = (page: Page) => page.locator("ul li");

test("a wrong login shows an error; a right one opens the list", async ({ page }) => {
  await mockBack(page, { loggedIn: false });
  await page.goto("/recruiter/login");
  await page.getByLabel("Usuario").fill("demo");
  await page.getByLabel("Contraseña").fill("mal");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByText("Usuario o contraseña incorrectos")).toBeVisible();

  await page.getByLabel("Contraseña").fill("ok");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/recruiter$/);
  await expect(rows(page)).toHaveCount(3);
});

test("the list shows every conversation and filters by status", async ({ page }) => {
  await mockBack(page);
  await page.goto("/recruiter");
  await expect(rows(page)).toHaveCount(3);
  await expect(rows(page).nth(2)).toContainText("Sin nombre");
  await expect(rows(page).nth(2)).toContainText("Voz");
  await expect(rows(page).nth(2)).toContainText("Inactivo");

  await page.getByRole("button", { name: /Descartado/ }).click();
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page)).toContainText("Jorge Ruiz");
  await page.getByRole("button", { name: /Todas/ }).click();
  await expect(rows(page)).toHaveCount(3);
});

test("the detail shows fields, summary and transcript", async ({ page }) => {
  await mockBack(page);
  await page.goto("/recruiter");
  await page.getByRole("link", { name: /Marta Gil/ }).click();
  await expect(page.getByRole("heading", { name: "Marta Gil" })).toBeVisible();
  await expect(page.getByText("Jornada completa", { exact: true })).toBeVisible();
  await expect(page.getByText("2 años · Glovo", { exact: true })).toBeVisible();
  await expect(page.getByText(DETAIL.summary)).toBeVisible();
  await expect(page.locator('[data-role="rita"]')).toHaveText("¿Tienes carné?");
  await expect(page.locator('[data-role="candidate"]')).toHaveText("Sí, desde 2019");
});

test("without a session the panel sends you to the login", async ({ page }) => {
  await mockBack(page, { loggedIn: false });
  await page.goto("/recruiter/a");
  await expect(page).toHaveURL(/\/recruiter\/login$/);
});

test("logout returns to the login", async ({ page }) => {
  await mockBack(page);
  await page.goto("/recruiter");
  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page).toHaveURL(/\/recruiter\/login$/);
});

test("the analytics add up the list: funnel, cities, knockouts and the daily chart", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-10-22T12:00:00Z"));
  await mockBack(page);
  await page.goto("/recruiter");
  const card = (title: string) => page.locator("div", { has: page.getByRole("heading", { name: title }) }).last();

  await expect(card("Embudo")).toContainText("Iniciadas3100%");
  await expect(card("Embudo")).toContainText("Completadas267%");
  await expect(card("Embudo")).toContainText("Cualificadas133%");
  await expect(card("Por ciudad")).toContainText(/Madrid2.*1 cualificada.*Sevilla1/);
  await expect(card("Motivos de descarte")).toContainText("Sin carné de conducir1100%");
  await expect(card("Canal y duración")).toContainText("4 min"); // (5 + 2) / 2, rounded

  const days = page.getByRole("listitem", { name: /cualificado/ });
  await expect(days).toHaveCount(14);
  await expect(days.nth(12)).toHaveAccessibleName(/21 oct: 1 cualificado, 1 pendiente, 1 descartado/);
  await expect(days.nth(13)).toHaveAccessibleName(/0 cualificado, 0 pendiente, 0 descartado/);
});

test("no conversations: no analytics, no division by zero", async ({ page }) => {
  await mockBack(page);
  await page.route("**/api/recruiter/conversations", (r) => r.fulfill({ json: [] }));
  await page.goto("/recruiter");
  await expect(page.getByText("No hay conversaciones.")).toBeVisible();
  await expect(page.getByText("Analítica")).toHaveCount(0);
  await expect(page.getByText("NaN")).toHaveCount(0);
});
