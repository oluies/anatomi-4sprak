// Rökprov för webbappen i en headless-webbläsare.
// Serverar katalogen över http (i stället för file://) så att sidan körs i samma
// slags kontext som på GitHub Pages, vänder ett kort, byter frågespråk till latin,
// svarar rätt på en quizfråga, söker i listan på alla tre förklaringsspråken och
// kräver att konsolen är fri från fel.
//
// Körs i CI av .github/workflows/ci.yml.
// Lokalt: npm install playwright && npx playwright install chromium
//         node tools/verify_app.mjs
import { chromium } from 'playwright';
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';

const ROOT = path.resolve(process.argv[2] || '.');
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.apkg': 'application/octet-stream'
};

const server = http.createServer(async (req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const file = path.join(ROOT, rel === '/' ? 'index.html' : rel);
  // Släpp inte ut något utanför den serverade katalogen.
  if (!file.startsWith(ROOT)) { res.writeHead(403).end(); return; }
  try {
    const body = await fs.readFile(file);
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end('not found');
  }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}/`;

const errors = [];
const warnings = [];
const browser = await chromium.launch();
const page = await browser.newPage();
page.on('console', m => {
  if (m.type() === 'error') errors.push(`[console] ${m.text()}`);
  // Varningar rapporteras men fäller inte bygget: Chromium byter version med
  // Playwright och avger då deprecation-varningar som inte rör den här koden.
  else if (m.type() === 'warning') warnings.push(m.text());
});
page.on('pageerror', e => errors.push(`[pageerror] ${e.message}`));
page.on('requestfailed', r => errors.push(`[requestfailed] ${r.url()} — ${r.failure()?.errorText}`));

const checks = [];
const check = (name, ok, detail = '') => checks.push({ name, ok: !!ok, detail: String(detail) });

try {
  await page.goto(base, { waitUntil: 'load' });

  // --- kortvyn ---
  check('423 termer laddade', (await page.textContent('#total')).includes('423'));
  check('svar dolda före vändning', (await page.getAttribute('#answers', 'class')).includes('hidden'));
  await page.click('#card');
  check('kortet vänds', !(await page.getAttribute('#answers', 'class')).includes('hidden'));
  check('tre svarsspråk visas', (await page.locator('#answers .ans').count()) === 3);

  // --- byt frågespråk till latin ---
  await page.selectOption('#front', 'la');
  const latin = (await page.textContent('#fterm')).trim();
  const isLatin = await page.evaluate(t => DATA.some(d => d.la === t), latin);
  check('frågan visas på latin', isLatin, latin);
  check('etiketten säger Latin', (await page.textContent('#flabel')).startsWith('Latin'));

  // --- quiz: svara rätt och kontrollera att poängen räknas ---
  await page.click('#modes button[data-mode="quiz"]');
  await page.waitForSelector('#qopts button');
  check('fyra svarsalternativ', (await page.locator('#qopts button').count()) === 4);
  // Läs det korrekta svaret ur appens eget tillstånd i stället för att härleda
  // det ur frågetexten — två termer kan dela form på ett av språken.
  const correct = await page.evaluate(() => state.qcur.item[state.qcur.ansLang]);
  await page.locator('#qopts button', { hasText: correct }).first().click();
  check('rätt svar räknas som rätt',
    (await page.textContent('#q_n')).trim() === '1' && (await page.textContent('#q_r')).trim() === '1',
    `frågor=${await page.textContent('#q_n')} rätt=${await page.textContent('#q_r')}`);
  await page.click('#qnext');
  check('nästa fråga laddas', (await page.textContent('#qterm')).trim().length > 0);

  // --- listan: rubriker och sökning på alla tre förklaringsspråken ---
  await page.click('#modes button[data-mode="list"]');
  const headers = await page.locator('#tbl thead th').allTextContents();
  check('kategorikolumnen har rätt rubrik', headers.at(-1) === 'Kategori', headers.join(' | '));
  for (const [term, label] of [['Bålens', 'svenska'], ['тулуба', 'ukrainska'], ['туловища', 'ryska']]) {
    await page.fill('#search', term);
    check(`sökning i ${label} förklaring ger träff`, (await page.locator('#tbl tbody tr').count()) > 0, term);
  }

  // --- sidfot, manifest och service worker ---
  check('nedladdningslänk till decket',
    (await page.textContent('a[href="data/anatomi-4sprak.apkg"]')).trim() === 'Ladda ner Anki-deck (.apkg)');
  check('manifestet är länkat', (await page.getAttribute('link[rel="manifest"]', 'href')) === 'manifest.webmanifest');
  check('manifestet svarar 200', (await (await page.request.get(base + 'manifest.webmanifest')).status()) === 200);
  check('decket svarar 200', (await (await page.request.get(base + 'data/anatomi-4sprak.apkg')).status()) === 200);
  // Service workern ska bara registreras över https — inte här.
  await page.waitForTimeout(500);
  check('ingen service worker över http',
    (await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length)) === 0);
} finally {
  await browser.close();
  server.close();
}

const failed = checks.filter(c => !c.ok);
for (const c of checks) console.log(`${c.ok ? 'OK  ' : 'FEL '} ${c.name}${c.detail ? '  — ' + c.detail : ''}`);
if (warnings.length) console.log(`\nKonsolvarningar (fäller inte bygget):\n  ${warnings.join('\n  ')}`);
if (errors.length) console.log(`\nKonsolfel:\n  ${errors.join('\n  ')}`);
console.log(`\n${checks.length - failed.length}/${checks.length} kontroller OK, ${errors.length} konsolfel.`);
process.exit(failed.length || errors.length ? 1 : 0);
