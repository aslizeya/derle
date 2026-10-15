import { expect, test } from "@playwright/test";

async function noHorizontalScroll(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

test("landing fits a phone and the demo starts", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await noHorizontalScroll(page);
  await page.getByRole("button", { name: "Örnek veriyle dene" }).first().click();
  await page.waitForURL(/\/w\/\d+\/yukle/);
  await expect(page.getByText("Tamamlandı")).toHaveCount(6, { timeout: 60_000 });
  await noHorizontalScroll(page);
});

test("bottom navigation and the more menu work on a phone", async ({ page }) => {
  await page.goto("/w/1");
  const tabbar = page.getByRole("navigation", { name: "Menü" }).last();
  await expect(tabbar.getByRole("link", { name: "Sor" })).toBeVisible();
  await tabbar.getByRole("button", { name: "Daha fazla" }).click();
  await page.getByRole("dialog").getByRole("link", { name: "Geçmiş" }).click();
  await expect(page.getByRole("heading", { name: "Geçmiş" })).toBeVisible();
  await noHorizontalScroll(page);
});
