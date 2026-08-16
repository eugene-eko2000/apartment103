const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1400, height: 1400 } });
  await page.goto("http://localhost:3002/en", { waitUntil: "load" });
  await page.waitForTimeout(1500);

  // Accept cookie consent if present
  const cookieBtn = page.locator("button", { hasText: /accept|allow/i }).first();
  try {
    await cookieBtn.click({ timeout: 3000 });
    console.log("clicked cookie consent");
  } catch (e) {
    console.log("no cookie consent banner found / or different text");
  }

  await page.screenshot({ path: "/private/tmp/claude-501/-Users-eko2000-103apartment-site-apartment103/edacd352-a47a-4096-b0d0-d63fd6bf4acb/scratchpad/explore1_top.png", fullPage: false });

  // Currency switcher
  const currencySwitcher = await page.locator("text=EUR").first();
  console.log("currency switcher visible:", await currencySwitcher.isVisible().catch(() => false));

  await browser.close();
})();
