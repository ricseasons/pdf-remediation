#!/usr/bin/env node
// Rebuild path, step 2: HTML -> tagged PDF with local Chromium, plus HTML accessibility checks.
//
// Usage: node render_pdf.cjs EDITION.html OUT.pdf REPORT.json [--footer "Short title · Reading edition"]
//
// All non-file network requests are blocked, so nothing in the document leaves the machine.
// Checks written to REPORT.json:
//   axe-core WCAG 2.0/2.1/2.2 A+AA rules, document overflow at 1280/640/320 CSS px,
//   WCAG 1.4.12 text-spacing override at 320 px, 200% text size, skip-link focus,
//   internal fragment links resolve, keyboard Tab sequence (first 60 stops).
const path = require('path');
const fs = require('fs');

function loadPlaywright() {
  for (const m of [process.env.PLAYWRIGHT_MODULE, 'playwright', 'playwright-core']) {
    if (!m) continue;
    try { return require(m); } catch (e) { /* try next */ }
  }
  throw new Error('playwright not found: run scripts/setup.sh or set PLAYWRIGHT_MODULE');
}

function findAxe() {
  const candidates = [process.env.AXE_PATH,
    path.join(process.env.HOME || '', '.cache', 'pdf-a11y', 'node_modules', 'axe-core', 'axe.min.js')];
  try { candidates.push(require.resolve('axe-core/axe.min.js')); } catch (e) { /* optional */ }
  return candidates.find(p => p && fs.existsSync(p));
}

(async () => {
  const [, , htmlPath, outPdf, reportPath, ...rest] = process.argv;
  if (!reportPath) { console.error('usage: render_pdf.cjs EDITION.html OUT.pdf REPORT.json [--footer TEXT]'); process.exit(2); }
  const fi = rest.indexOf('--footer');
  const footer = fi >= 0 ? rest[fi + 1] : '';
  const esc = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  await page.route('**/*', r => r.request().url().startsWith('file:') || r.request().url().startsWith('data:') ? r.continue() : r.abort());
  const url = 'file://' + path.resolve(htmlPath);
  await page.goto(url);
  await page.pdf({
    path: outPdf, tagged: true, outline: true, printBackground: true, preferCSSPageSize: true,
    displayHeaderFooter: !!footer, headerTemplate: '<span></span>',
    footerTemplate: footer ? `<div style="font-family:Arial;font-size:8px;color:#435766;width:100%;text-align:center">${esc(footer)} · <span class="pageNumber"></span> / <span class="totalPages"></span></div>` : '<span></span>',
  });
  const report = { pdf: outPdf };
  const axePath = findAxe();
  if (axePath) {
    await page.addScriptTag({ path: axePath });
    const axe = await page.evaluate(async () => await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] } }));
    report.axe = { version: axe.testEngine.version, violations: axe.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, targets: v.nodes.slice(0, 5).map(n => n.target.join(' ')) })), incomplete: axe.incomplete.map(v => ({ id: v.id, nodes: v.nodes.length })), passes: axe.passes.length };
  } else {
    report.axe = { error: 'axe-core not found; run scripts/setup.sh or set AXE_PATH' };
  }
  const overflow = () => page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, viewport: innerWidth, overflow: document.documentElement.scrollWidth > innerWidth + 1 }));
  report.layout = [];
  for (const width of [1280, 640, 320]) { await page.setViewportSize({ width, height: 900 }); report.layout.push({ width, ...(await overflow()) }); }
  await page.addStyleTag({ content: '*{line-height:1.5 !important;letter-spacing:.12em !important;word-spacing:.16em !important}p{margin-bottom:2em !important}' });
  report.layout.push({ test: 'WCAG 1.4.12 text spacing at 320px', ...(await overflow()) });
  await page.goto(url);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.addStyleTag({ content: 'html{font-size:200% !important}' });
  report.layout.push({ test: '200% text size at 1280px', ...(await overflow()) });
  await page.goto(url);
  await page.keyboard.press('Tab');
  const first = await page.evaluate(() => ({ tag: document.activeElement.tagName, text: document.activeElement.textContent.trim().slice(0, 60), href: document.activeElement.getAttribute('href') }));
  let skip = null;
  if (first.href && first.href.startsWith('#')) { await page.keyboard.press('Enter'); skip = await page.evaluate(() => ({ focused: document.activeElement.id || document.activeElement.tagName })); }
  report.keyboard = { firstTabStop: first, skipLinkResult: skip };
  const tabs = [];
  await page.goto(url);
  for (let i = 0; i < 60; i++) { await page.keyboard.press('Tab'); tabs.push(await page.evaluate(() => { const a = document.activeElement; return (a.getAttribute('role') || a.tagName) + ': ' + (a.getAttribute('aria-label') || a.textContent.trim().slice(0, 50)); })); }
  report.keyboard.tabSequence = tabs;
  report.fragmentLinks = await page.evaluate(() => [...document.querySelectorAll('a[href^="#"]')].map(a => ({ text: a.textContent.trim().slice(0, 60), target: a.hash, exists: !!document.getElementById(decodeURIComponent(a.hash.slice(1))) })).filter(l => !l.exists));
  report.network = 'all non-file requests blocked';
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  const v = report.axe.violations || [];
  console.log(JSON.stringify({ pdf: outPdf, axeViolations: v.map(x => `${x.id}(${x.nodes})`), overflow: report.layout.filter(l => l.overflow), brokenFragments: report.fragmentLinks.length, firstTab: first.text }));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
