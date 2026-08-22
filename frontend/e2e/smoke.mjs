/**
 * End-to-end smoke test against the running dev servers.
 *
 *   Terminal 1: cd backend  && .venv/bin/python manage.py runserver 8000
 *   Terminal 2: cd frontend && npm run dev
 *   Terminal 3: node e2e/smoke.mjs
 *
 * Exercises the paths a screenshot cannot: filling the form, submitting it,
 * and downloading the generated PDF.
 */
import { chromium } from "playwright";
import { mkdtempSync, statSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.env.BASE_URL ?? "http://localhost:5173";
const results = [];
const record = (name, ok = true, detail = "") => {
  results.push({ name, ok, detail });
  console.log(`${ok ? "  PASS" : "  FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
};

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1500, height: 1000 },
  acceptDownloads: true,
});
const page = await context.newPage();

const consoleErrors = [];
page.on("pageerror", (e) => consoleErrors.push(String(e)));
page.on("console", (m) => {
  if (m.type() === "error") consoleErrors.push(m.text());
});

try {
  await page.goto(BASE, { waitUntil: "networkidle" });
  record("app loads", await page.getByText("Enter a trip to begin").isVisible());

  // --- fill the form ---
  await page.getByLabel("Current location").fill("Dallas, Texas");
  await page.getByLabel("Pickup location").fill("Oklahoma City, Oklahoma");
  await page.getByLabel("Dropoff location").fill("Chicago, Illinois");
  await page.getByLabel("Cycle hours used").fill("20");
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "Plan trip" }).click();
  await page.getByText("Driver's Daily Logs").waitFor({ timeout: 90_000 });
  record("form submit produces a plan");

  // --- the URL becomes shareable ---
  const url = page.url();
  record("URL becomes a shareable /trip/<id>", /\/trip\/[0-9a-f-]{36}$/i.test(url), url.slice(-45));

  // --- results are coherent ---
  const sheets = await page.locator("svg[role='img'][aria-label*=\"daily log\"]").count();
  record("a log sheet is drawn per day", sheets >= 1, `${sheets} sheets`);

  const totals = await page.locator("text=/^= 24\\.00$/").count();
  record("every sheet totals 24.00 hours", totals === sheets, `${totals}/${sheets}`);

  const penLines = await page.locator("svg path[stroke='#1b3a6b']").count();
  record("duty line is drawn on each sheet", penLines >= sheets, `${penLines} paths`);

  // --- PDF export actually produces a file ---
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 45_000 }),
    page.getByRole("button", { name: "Download PDF" }).click(),
  ]);
  const dir = mkdtempSync(join(tmpdir(), "eld-"));
  const file = join(dir, download.suggestedFilename());
  await download.saveAs(file);
  const size = statSync(file).size;
  const header = readFileSync(file).subarray(0, 5).toString();
  record("PDF downloads and is a valid PDF", header === "%PDF-" && size > 20_000,
         `${header} ${(size / 1024).toFixed(0)} KB`);

  // --- reload the shared link ---
  await page.goto(url, { waitUntil: "networkidle" });
  await page.getByText("Driver's Daily Logs").waitFor({ timeout: 30_000 });
  const restoredSheets = await page.locator("svg[role='img'][aria-label*=\"daily log\"]").count();
  record("shared link restores the trip", restoredSheets === sheets);

  const openDropdowns = await page.locator("ul li button").count();
  record("no autocomplete list opens on restore", openDropdowns === 0, `${openDropdowns} items`);

  record("no console errors", consoleErrors.length === 0, consoleErrors.slice(0, 2).join(" | "));
} catch (error) {
  record("run completed without throwing", false, String(error).split("\n")[0]);
} finally {
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
