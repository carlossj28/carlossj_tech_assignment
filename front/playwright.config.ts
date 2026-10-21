import { defineConfig } from "@playwright/test";

// E2E against `next dev` with the back mocked via page.route (tests/chat.spec.ts).
export default defineConfig({
  testDir: "tests",
  // CHROMIUM_PATH: optional, to use a preinstalled browser instead of `npx playwright install`.
  use: { baseURL: "http://localhost:3100", launchOptions: { executablePath: process.env.CHROMIUM_PATH } },
  webServer: { command: "npm run dev -- --port 3100", url: "http://localhost:3100", reuseExistingServer: true },
});
