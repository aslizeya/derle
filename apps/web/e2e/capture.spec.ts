import { mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Page, test } from "@playwright/test";

/**
 * Regenerates the README screenshots and GIF frames from the real app:
 *   npm run capture && python ../../tools/media/make_gif.py
 * Runs only in the "capture" project, never as part of the e2e suite.
 */
test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

const here = dirname(fileURLToPath(import.meta.url));
const SHOTS = resolve(here, "../../../docs/screenshots");
const FRAMES = resolve(here, "../test-results/frames");
mkdirSync(SHOTS, { recursive: true });

let workspace = "";

async function shot(page: Page, name: string, fullPage = false) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(400);
  await page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage });
}

async function recordFrames(page: Page, name: string, durationMs: number, everyMs = 180) {
  const dir = join(FRAMES, name);
  mkdirSync(dir, { recursive: true });
  const start = Date.now();
  for (let i = 0; Date.now() - start < durationMs; i++) {
    await page.screenshot({ path: join(dir, `${String(i).padStart(4, "0")}.png`) });
    await page.waitForTimeout(everyMs);
  }
}

test("landing and its before/after animation", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await recordFrames(page, "landing", 13_000);
  // The still shows the finished "after" state: reduced motion renders it directly.
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.reload();
  await shot(page, "landing");
});

test("live upload of the demo ledger", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Örnek veriyle dene" }).first().click();
  await page.waitForURL(/\/w\/\d+\/yukle/);
  workspace = /\/w\/(\d+)\//.exec(page.url())![1]!;
  await recordFrames(page, "upload", 9_000, 150);
  await expect(page.getByText("Tamamlandı")).toHaveCount(6, { timeout: 60_000 });
  await shot(page, "upload");
});

test("review, matching, table, ask, dashboard, quality, history", async ({ page }) => {
  const base = `/w/${workspace}`;

  const uploads = (await (await page.request.get(`/api/v1/workspaces/${workspace}/uploads`)).json()) as {
    id: number;
    filename: string;
  }[];
  const mayis = uploads.find((u) => u.filename.startsWith("mayis"))!;
  await page.goto(`${base}/yuklemeler/${mayis.id}`);
  await expect(page.getByText("Sütunlar nasıl tanındı")).toBeVisible();
  await page.locator("tbody tr").nth(18).locator("td button").first().click();
  await shot(page, "review");

  await page.goto(`${base}/eslestirme`);
  await expect(page.getByText(/soru kaldı/)).toBeVisible();
  await shot(page, "matching");

  await page.goto(base);
  await page.getByRole("link", { name: /ocak_2026/ }).click();
  await expect(page.getByRole("columnheader", { name: /Eşleşmiş müşteri/ })).toBeVisible();
  await page.locator("tbody tr").nth(2).locator("td").nth(2).getByRole("button").click();
  await expect(page.getByRole("dialog").getByText("Dosyadaki hali")).toBeVisible();
  await shot(page, "provenance");
  await page.keyboard.press("Escape");

  await page.goto(`${base}/sor`);
  await page.getByRole("button", { name: "Geçen ay en çok kim borçlandı?" }).click();
  const answer = page.locator("article").first();
  await expect(answer.getByText("Kural tabanlı")).toBeVisible();
  await answer.getByText("Çalıştırılan SQL").click();
  await shot(page, "ask", true);

  await page.goto(`${base}/panel`);
  await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
  await shot(page, "dashboard", true);

  await page.goto(base);
  await page.getByRole("link", { name: /ocak_2026/ }).click();
  await page.getByRole("link", { name: /Kalite skoru/ }).click();
  await expect(page.getByRole("heading", { name: "Veri kalitesi" })).toBeVisible();
  await shot(page, "quality");

  await page.goto(`${base}/gecmis`);
  await expect(page.getByText("Şu anki durum")).toBeVisible();
  await shot(page, "history");
});

test("dark mode and phone", async ({ browser }) => {
  const dark = await browser.newPage({ colorScheme: "dark", viewport: { width: 1360, height: 860 } });
  await dark.goto(`http://127.0.0.1:3100/w/${workspace}/panel`);
  await expect(dark.locator(".recharts-bar-rectangle").first()).toBeVisible();
  await shot(dark, "dashboard-dark");
  await dark.goto(`http://127.0.0.1:3100/w/${workspace}/eslestirme`);
  await expect(dark.getByText(/soru kaldı/)).toBeVisible();
  await shot(dark, "matching-dark");
  await dark.close();

  const phone = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  await phone.goto(`http://127.0.0.1:3100/w/${workspace}/eslestirme`);
  await expect(phone.getByText(/soru kaldı/)).toBeVisible();
  await shot(phone, "phone-matching");
  await phone.goto(`http://127.0.0.1:3100/w/${workspace}/sor`);
  await phone.getByRole("button", { name: "En çok borcu olan 5 müşteri" }).click();
  await expect(phone.locator("article").first().getByText("Kural tabanlı")).toBeVisible();
  await shot(phone, "phone-ask");
  await phone.close();
});
