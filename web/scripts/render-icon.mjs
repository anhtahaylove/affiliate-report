// Rasterize SVG icon sang PNG bằng Chromium của Playwright.
// Repo không có cairosvg; Playwright thì đã có sẵn cho e2e nên dùng lại, không thêm phụ thuộc.
// Nhận spec JSON qua stdin: [{ svg, out, size, round? }]
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";

const specs = JSON.parse(readFileSync(0, "utf8"));
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 64, height: 64 } });

for (const spec of specs) {
  const svg = readFileSync(spec.svg, "utf8").replace(/width="\d+" height="\d+"/, `width="${spec.size}" height="${spec.size}"`);
  // clip-path bo tròn cho ic_launcher_round: Android không tự bo bản mipmap này.
  const clip = spec.round ? `clip-path: circle(50% at 50% 50%);` : "";
  await page.setViewportSize({ width: spec.size, height: spec.size });
  await page.setContent(`<body style="margin:0;width:${spec.size}px;height:${spec.size}px">
    <div style="width:${spec.size}px;height:${spec.size}px;${clip}">${svg}</div></body>`);
  await page.locator("div").first().screenshot({ path: spec.out, omitBackground: true });
}

await browser.close();
console.log(`rendered ${specs.length}`);
