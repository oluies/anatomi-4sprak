// Rökprov för webbappen i en headless-webbläsare.
// Serverar katalogen över http (i stället för file://) så att sidan körs i samma
// slags kontext som på GitHub Pages, vänder ett kort, byter frågespråk till latin,
// svarar rätt på en quizfråga, söker i listan på alla tre förklaringsspråken och
// kräver att konsolen är fri från fel.
//
// Körs i CI av .github/workflows/ci.yml.
// Lokalt: npm install playwright && npx playwright install chromium
//         node tools/verify_app.mjs
import { chromium, devices } from 'playwright';
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
  // resolve mot '.' + rel så att ../ i sökvägen normaliseras bort innan
  // jämförelsen, och kräv separatorn — annars matchar en systerkatalog med
  // samma prefix som ROOT.
  const file = path.resolve(ROOT, '.' + (rel === '/' ? '/index.html' : rel));
  if (file !== ROOT && !file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
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
  // Jämför mot JSON-filen i stället för en hårdkodad siffra: en ny term ska
  // inte fälla bygget, men appen ska aldrig visa ett annat antal än den laddat.
  const jsonTerms = await (await page.request.get(base + 'data/anatomi-termer.json')).json();
  const inlineCount = await page.evaluate(() => DATA.length);
  check('index.html har lika många termer som JSON-filen',
    inlineCount === jsonTerms.length, `index.html=${inlineCount} json=${jsonTerms.length}`);
  check('sidfoten visar antalet laddade termer',
    (await page.textContent('#total')).includes(String(inlineCount)), await page.textContent('#total'));
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
  // Klicka via exakt textmatchning i sidan. Playwrights hasText matchar delsträngar,
  // och datan har 82 par där ett svar ryms i ett annat ("вена" i "яремна вена"),
  // vilket skulle klicka fel knapp ungefär varannan gång.
  const clicked = await page.evaluate(() => {
    const correct = state.qcur.item[state.qcur.ansLang];
    const btn = [...document.getElementById('qopts').children]
      .find(b => b.textContent === correct);
    if (!btn) return null;
    btn.click();
    return correct;
  });
  check('rätt alternativ fanns bland knapparna', clicked !== null, clicked || '');
  check('rätt svar räknas som rätt',
    (await page.textContent('#q_n')).trim() === '1' && (await page.textContent('#q_r')).trim() === '1',
    `frågor=${await page.textContent('#q_n')} rätt=${await page.textContent('#q_r')}`);
  await page.click('#qnext');
  check('nästa fråga laddas', (await page.textContent('#qterm')).trim().length > 0);

  // --- listan: rubriker och sökning på alla tre förklaringsspråken ---
  await page.click('#modes button[data-mode="list"]');
  const headers = await page.locator('#tbl thead th').allTextContents();
  check('kategorikolumnen har rätt rubrik', headers.at(-1) === 'Kategori', headers.join(' | '));
  // Sökorden hämtas ur datan i stället för att hårdkodas, och förväntat antal
  // rader räknas ut i sidan — så fångas både en trasig och en alltid-sann filtrering.
  for (const field of ['def_sv', 'def_uk', 'def_ru']) {
    const probe = await page.evaluate(f => {
      const langs = ['sv', 'la', 'uk', 'ru'];
      // Ett ord som bara finns i förklaringen, aldrig i något termfält.
      for (const d of DATA) {
        for (const w of String(d[f]).toLowerCase().match(/\p{L}{6,}/gu) || []) {
          if (DATA.some(x => langs.some(k => String(x[k]).toLowerCase().includes(w)))) continue;
          const expected = DATA.filter(x =>
            langs.some(k => String(x[k]).toLowerCase().includes(w)) ||
            ['def_sv', 'def_uk', 'def_ru'].some(k => String(x[k] || '').toLowerCase().includes(w))
          ).length;
          return { word: w, expected, n: d.n };
        }
      }
      return null;
    }, field);
    if (!probe) { check(`hittade ett testord för ${field}`, false); continue; }
    await page.fill('#search', probe.word);
    const rows = await page.locator('#tbl tbody tr').count();
    const firstCol = await page.locator('#tbl tbody tr td:first-child').allTextContents();
    check(`sökning i ${field} ger exakt ${probe.expected} rad(er)`, rows === probe.expected,
      `"${probe.word}" gav ${rows}`);
    check(`sökning i ${field} innehåller rätt term`, firstCol.includes(String(probe.n)), `n=${probe.n}`);
  }
  // Kontroll att filtret inte alltid är sant.
  await page.fill('#search', 'zzzqqqxyz');
  check('sökning utan träff ger noll rader', (await page.locator('#tbl tbody tr').count()) === 0);
  await page.fill('#search', '');

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

  // --- svarsspråken: svenska ska visas för varje frågespråk utom svenska ---
  // Regression: state.backs saknade "sv", så svenska kunde aldrig bli svar.
  await page.click('#modes button[data-mode="card"]');
  for (const front of ['sv', 'la', 'uk', 'ru']) {
    await page.selectOption('#front', front);
    await page.evaluate(() => { if (!state.flipped) document.getElementById('card').click(); });
    const shown = await page.evaluate(() => {
      const vals = [...document.querySelectorAll('#answers .ansval')].map(e => e.textContent);
      return { vals, sv: state.current.sv, langs: state.backs.filter(k => k !== state.front) };
    });
    check(`frågespråk ${front}: tre svarsspråk`, shown.langs.length === 3, shown.langs.join(','));
    if (front !== 'sv') {
      check(`frågespråk ${front}: svenska visas som svar`, shown.vals.includes(shown.sv), shown.sv);
    }
  }

  // --- hopfällbara inställningar ---
  const settingsOpen = () => page.locator('#settings').isVisible();
  check('inställningarna är utfällda på stor skärm', await settingsOpen());
  const tallHeader = await page.evaluate(() => document.querySelector('header').offsetHeight);
  await page.click('#togglesettings');
  check('knappen fäller ihop inställningarna', !(await settingsOpen()));
  check('sammanfattningen visas i stället', await page.locator('#summary').isVisible());
  const shortHeader = await page.evaluate(() => document.querySelector('header').offsetHeight);
  check('hopfällt ger lägre sidhuvud', shortHeader < tallHeader, `${shortHeader}px < ${tallHeader}px`);
  check('lägesväljaren är kvar när det är hopfällt', await page.locator('#modes').isVisible());
  await page.click('#summary');
  check('klick på sammanfattningen fäller ut igen', await settingsOpen());

  // --- kategorinamnen ska följa gränssnittsspråket ---
  const catByUi = {};
  for (const ui of ['sv', 'uk', 'ru', 'en']) {
    await page.selectOption('#ui', ui);
    catByUi[ui] = (await page.locator('#cats .chip').first().textContent()).trim();
  }
  const distinct = new Set(Object.values(catByUi));
  check('kategorinamnen översätts med gränssnittet', distinct.size === 4,
    Object.entries(catByUi).map(([k, v]) => `${k}=${v}`).join(' | '));
  check('ukrainskt kategorinamn är kyrilliskt', /[\u0400-\u04FF]/.test(catByUi.uk), catByUi.uk);
  check('engelskt kategorinamn är latinskt', /^[A-Za-z]/.test(catByUi.en), catByUi.en);
  // listkolumnen och kortetiketten ska följa med
  await page.selectOption('#ui', 'uk');
  await page.click('#modes button[data-mode="list"]');
  const lastCol = (await page.locator('#tbl tbody tr:first-child td:last-child').textContent()).trim();
  check('listans kategorikolumn är översatt', /[\u0400-\u04FF]/.test(lastCol), lastCol);
  // sökning på ett översatt kategorinamn ska ge träff
  const uaCat = await page.evaluate(() => CATS['Leder och muskler'].uk);
  await page.fill('#search', uaCat.split(' ')[0]);
  const catRows = await page.locator('#tbl tbody tr').count();
  const expectCat = await page.evaluate(() => DATA.filter(d => d.cat === 'Leder och muskler').length);
  check('sökning på översatt kategorinamn ger träff', catRows >= expectCat, `${catRows} rader, väntade minst ${expectCat}`);
  await page.fill('#search', '');
  await page.selectOption('#ui', 'sv');
  await page.click('#modes button[data-mode="card"]');

  // --- språkkonfigurationen styr appen ---
  const cfg = await page.evaluate(() => ({
    langs: Object.keys(LANGS), defs: DEFFIELDS, uis: Object.keys(UILANGS),
    backs: state.backs, cats: Object.keys(CATS).length
  }));
  const sprak = await (await page.request.get(base + 'data/sprak.json')).json();
  const wantTerm = Object.keys(sprak).filter(k => sprak[k].term);
  const wantDef = Object.keys(sprak).filter(k => sprak[k].forklaring).map(k => 'def_' + k);
  const wantUi = Object.keys(sprak).filter(k => sprak[k].granssnitt);
  check('termspråken kommer från data/sprak.json',
    JSON.stringify(cfg.langs) === JSON.stringify(wantTerm), cfg.langs.join(','));
  check('förklaringsfälten kommer från data/sprak.json',
    JSON.stringify(cfg.defs) === JSON.stringify(wantDef), cfg.defs.join(','));
  check('gränssnittsspråken kommer från data/sprak.json',
    JSON.stringify(cfg.uis) === JSON.stringify(wantUi), cfg.uis.join(','));
  const kategorier = await (await page.request.get(base + 'data/kategorier.json')).json();
  check('kategoriöversättningarna är i synk', cfg.cats === Object.keys(kategorier).length,
    `${cfg.cats} i appen, ${Object.keys(kategorier).length} i filen`);

  // --- sidfoten: upphovsperson, licens och attribution ---
  const foot = await page.evaluate(() => ({
    meta: document.getElementById('footmeta').textContent.replace(/\s+/g, ' ').trim(),
    hrefs: [...document.querySelectorAll('footer a')].map(a => a.getAttribute('href'))
  }));
  check('sidfoten anger upphovsperson', foot.meta.includes('Örjan Lundberg'), foot.meta);
  check('sidfoten anger licensen', foot.meta.includes('CC BY-SA 4.0'));
  check('sidfoten attribuerar Wikipedia', foot.meta.includes('Wikipedia'));
  for (const [what, href] of [
    ['licenslänk', 'https://creativecommons.org/licenses/by-sa/4.0/deed.sv'],
    ['Wikipedia-artikeln', 'https://sv.wikipedia.org/wiki/M%C3%A4nniskans_anatomi'],
    ['källkoden', 'https://github.com/oluies/anatomi-4sprak'],
    ['donationslänk', 'https://donate.wikimedia.org/'],
    ['deck-nedladdning', 'data/anatomi-4sprak.apkg']]) {
    check(`sidfoten länkar till ${what}`, foot.hrefs.includes(href), href);
  }
  // sidfotens texter ska översättas
  await page.selectOption('#ui', 'uk');
  const ukFoot = (await page.textContent('#footmeta')).trim();
  check('sidfoten översätts', /[\u0400-\u04FF]/.test(ukFoot) && ukFoot.includes('Örjan Lundberg'), ukFoot);
  await page.selectOption('#ui', 'sv');

  // --- telefonvy: hopfällt från start ---
  const phone = await browser.newContext({ ...devices['iPhone 13'] });
  const small = await phone.newPage();
  small.on('pageerror', e => errors.push(`[pageerror telefon] ${e.message}`));
  await small.goto(base, { waitUntil: 'load' });
  check('telefon: hopfällt från start',
    (await small.getAttribute('#togglesettings', 'aria-expanded')) === 'false');
  check('telefon: sammanfattningen syns', await small.locator('#summary').isVisible());
  check('telefon: lägesväljaren syns', await small.locator('#modes').isVisible());
  const cardTop = await small.evaluate(() => Math.round(document.querySelector('.card').getBoundingClientRect().top));
  const vh = await small.evaluate(() => window.innerHeight);
  check('telefon: kortet syns utan att man scrollar', cardTop < vh / 2, `kortet börjar ${cardTop}px av ${vh}px`);
  // pluralformerna i sammanfattningen — panelen måste fällas ut för att nå väljaren
  await small.click('#togglesettings');
  await small.selectOption('#ui', 'ru');
  await small.click('#togglesettings');
  const ruSummary = (await small.textContent('#summary')).trim();
  // Förväntad form räknas ut här, oberoende av sidans egen plural(), och
  // antalet läses ur datan så att en ny term inte fäller bygget.
  const ruForms = ['карточка', 'карточки', 'карточек'];
  const ruPlural = n => {
    const t = n % 10, h = n % 100;
    if (t === 1 && h !== 11) return ruForms[0];
    if (t >= 2 && t <= 4 && (h < 12 || h > 14)) return ruForms[1];
    return ruForms[2];
  };
  const n = await small.evaluate(() => DATA.length);
  check('telefon: ryska pluralformer i sammanfattningen',
    ruSummary.includes('Все категории') && ruSummary.includes(`${n} ${ruPlural(n)}`),
    `väntade "${n} ${ruPlural(n)}" i: ${ruSummary}`);
  // Själva böjningsregeln, mot oberoende facit.
  const pluralCases = { 1: 0, 2: 1, 4: 1, 5: 2, 11: 2, 12: 2, 21: 0, 22: 1, 25: 2, 101: 0, 111: 2, 424: 1 };
  const pluralActual = await small.evaluate(
    (ns) => ns.map(x => plural(x, ['ett', 'få', 'många'])), Object.keys(pluralCases).map(Number));
  const want = Object.values(pluralCases).map(i => ['ett', 'få', 'många'][i]);
  check('böjningsregeln för ryska/ukrainska räkneord',
    JSON.stringify(pluralActual) === JSON.stringify(want),
    `${pluralActual.join(',')} vs ${want.join(',')}`);
  await phone.close();
} catch (e) {
  // Utan detta dör skriptet på ett rått Playwright-stacktrace och operatören
  // ser aldrig vilka kontroller som hann gå igenom.
  errors.push(`[avbrott] ${e.message}`);
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
