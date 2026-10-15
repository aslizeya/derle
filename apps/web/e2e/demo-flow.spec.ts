import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

/**
 * The whole product, the way a first-time visitor meets it: landing → "Örnek veriyle dene"
 * → six messy files processed live → answer a matching question → trace a value to its
 * source → ask a question → dashboard → quality → restore an earlier version.
 */
test.describe.configure({ mode: "serial" });

let workspace = "";

async function openWorkspacePage(page: Page, path: string) {
  await page.goto(`/w/${workspace}${path}`);
  await page.waitForLoadState("networkidle");
}

test("landing → demo: six messy files are recognised, cleaned and summarised live", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Dağınık defterden düzenli kayda.");
  await expect(page.getByText("mart_2026.xlsx")).toBeVisible();
  await page.waitForLoadState("networkidle");

  await page.getByRole("button", { name: "Örnek veriyle dene" }).first().click();
  await page.waitForURL(/\/w\/\d+\/yukle/);
  workspace = /\/w\/(\d+)\//.exec(page.url())![1]!;

  const cards = page.locator("article").filter({ hasText: "_2026" });
  await expect(cards).toHaveCount(6, { timeout: 30_000 });
  await expect(page.getByText("Tamamlandı")).toHaveCount(6, { timeout: 60_000 });

  // The recognition story is visible: column chips and the duplicate count.
  await expect(page.getByText(/mükerrer kayıt ayıklandı/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /eşleşme sorusu var/ })).toBeVisible();
});

test("matching questions can be answered with the keyboard and undone", async ({ page }) => {
  await openWorkspacePage(page, "/eslestirme");
  const remaining = page.getByText(/soru kaldı/);
  await expect(remaining).toBeVisible();
  const before = Number((await remaining.textContent())!.match(/\d+/)![0]);

  await page.keyboard.press("f");
  await expect(page.getByText("Ayrı tutuldu")).toBeVisible();
  await expect(remaining).toHaveText(new RegExp(`^${before - 1} `));

  await page.keyboard.press("z");
  await expect(remaining).toHaveText(new RegExp(`^${before} `));
});

test("every clean value traces back to its source row", async ({ page }) => {
  await openWorkspacePage(page, "");
  await page.getByRole("link", { name: /ocak_2026/ }).click();
  await expect(page.getByRole("columnheader", { name: /Eşleşmiş müşteri/ })).toBeVisible();

  await page.locator("tbody tr").first().locator("td").nth(2).getByRole("button").click();
  const panel = page.getByRole("dialog");
  await expect(panel.getByText("Bu değer nereden geldi?")).toBeVisible();
  await expect(panel.getByText("Dosyadaki hali")).toBeVisible();
  await expect(panel.getByText("ocak_2026.xlsx")).toBeVisible();
});

test("questions in Turkish are answered with the SQL shown", async ({ page }) => {
  await openWorkspacePage(page, "/sor");
  await page.getByRole("button", { name: "Kaç müşterim var?" }).click();
  const answer = page.locator("article").first();
  await expect(answer.getByText("Kural tabanlı")).toBeVisible();
  await answer.getByText("Çalıştırılan SQL").click();
  await expect(answer.locator("pre")).toContainText("COUNT(DISTINCT");

  await page.getByPlaceholder(/Örneğin/).fill("Ahmet Demir'in borcu ne kadar?");
  await page.keyboard.press("Enter");
  await expect(page.getByText("“Ahmet Demir” adında bir müşteri bulamadım", { exact: false })).toBeVisible();
});

test("dashboard and quality report are generated from the data", async ({ page }) => {
  await openWorkspacePage(page, "/panel");
  await expect(page.getByText("Açık bakiye", { exact: true })).toBeVisible();
  await expect(page.getByText("Aylık borç ve ödeme")).toBeVisible();
  await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();

  await openWorkspacePage(page, "");
  await expect(page.getByTitle("Kalite skoru").first()).toBeVisible(); // ring on the dataset card
  await page.getByRole("link", { name: /ocak_2026/ }).click();
  await page.getByRole("link", { name: /Kalite skoru/ }).click();
  await expect(page.getByRole("heading", { name: "Veri kalitesi" })).toBeVisible();
  await expect(page.getByText(/eşleşmesi onay bekliyor/)).toBeVisible();
});

test("history restores an earlier state as a new version", async ({ page }) => {
  await openWorkspacePage(page, "/gecmis");
  await expect(page.getByText("Şu anki durum")).toBeVisible();
  await page.getByRole("button", { name: "Bu duruma dön" }).nth(1).click();
  await page.getByRole("dialog").getByRole("button", { name: "Bu duruma dön" }).click();
  await expect(page.getByText(/versiyona geri dönüldü/)).toBeVisible();
});

test("key pages have no serious accessibility violations", async ({ page }) => {
  const pages = ["", "/eslestirme", "/sor", "/panel", "/gecmis", "/yukle"].map((p) => `/w/${workspace}${p}`);
  for (const path of ["/", ...pages]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    const report = serious.flatMap((v) =>
      v.nodes.map((n) => `${path} ${v.id}: ${n.target.join(" ")} — ${n.any[0]?.message ?? ""}`),
    );
    expect(report).toEqual([]);
  }
});
