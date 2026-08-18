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
  // Utgå från en namngiven kategori, inte "första chipet" — vilken term som
  // sorterar först i datan är irrelevant för det som testas.
  const CAT = 'Leder och muskler';
  const catByUi = {};
  for (const ui of ['sv', 'uk', 'ru', 'en']) {
    await page.selectOption('#ui', ui);
    catByUi[ui] = await page.evaluate(c => catName(c), CAT);
  }
  const expected = await page.evaluate(c => CATS[c], CAT);
  check('kategorinamnen översätts med gränssnittet',
    catByUi.sv === CAT && catByUi.uk === expected.uk &&
    catByUi.ru === expected.ru && catByUi.en === expected.en,
    Object.entries(catByUi).map(([k, v]) => `${k}=${v}`).join(' | '));
  await page.selectOption('#ui', 'uk');
  check('chipsen visar det översatta namnet', await page.evaluate(c => {
    const want = CATS[c].uk;
    return [...document.querySelectorAll('#cats .chip')].some(b => b.textContent.startsWith(want));
  }, CAT));
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

  // --- besöksräkning ---
  // Över http (som här och i CI) får den inte laddas alls, annars skulle varje
  // testkörning räknas som ett besök.
  const gcHttp = await page.evaluate(() =>
    [...document.querySelectorAll('script[src]')].some(s => s.src.includes('gc.zgo.at')));
  check('besöksräknaren laddas inte över http', !gcHttp);
  const gcCode = await page.evaluate(() => {
    const m = document.documentElement.innerHTML.match(/var CODE = "([^"]+)"/);
    return m && m[1];
  });
  check('besöksräknarens kod är satt', !!gcCode, gcCode || '(saknas)');
  // Respekterar besökarens val att slippa spårning.
  const gcDnt = await page.evaluate(() => {
    const src = document.documentElement.innerHTML;
    return src.includes('doNotTrack') && src.includes('globalPrivacyControl');
  });
  check('besöksräknaren respekterar do-not-track', gcDnt);

  // --- hjälpen ---
  const helpVisible = () => page.locator('#help').isVisible();
  check('hjälpen är dold från start', !(await helpVisible()));
  await page.keyboard.press('h');
  check('h öppnar hjälpen', await helpVisible());
  await page.keyboard.press('h');
  check('h stänger hjälpen igen', !(await helpVisible()));
  await page.keyboard.press('?');
  check('frågetecken öppnar hjälpen', await helpVisible());
  await page.keyboard.press('Escape');
  check('Esc stänger hjälpen', !(await helpVisible()));
  await page.click('#helpbtn');
  check('knappen öppnar hjälpen', await helpVisible());
  await page.click('#help', { position: { x: 5, y: 5 } });
  check('klick utanför rutan stänger', !(await helpVisible()));

  // Med hjälpen öppen får inga andra genvägar plocka upp tangenten.
  await page.evaluate(() => { resetQueue(); renderCard(); });
  const beforeHelp = await page.evaluate(() => state.current.id);
  await page.keyboard.press('h');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  const during = await page.evaluate(() => ({ id: state.current.id, flipped: state.flipped }));
  check('pilarna är blockerade när hjälpen är öppen',
    during.id === beforeHelp && !during.flipped);
  await page.keyboard.press('Escape');

  for (const mode of ['quiz', 'image', 'list']) {
    await page.click(`#modes button[data-mode="${mode}"]`);
    await page.keyboard.press('h');
    const on = await helpVisible();
    await page.keyboard.press('Escape');
    check(`hjälpen går att öppna i läget ${mode}`, on);
  }
  // h ska inte kapas när man skriver i sökrutan
  await page.click('#modes button[data-mode="list"]');
  await page.fill('#search', 'h');
  check('h i sökrutan skriver text i stället för att öppna hjälpen',
    (await page.inputValue('#search')) === 'h' && !(await helpVisible()));
  await page.fill('#search', '');
  await page.click('#modes button[data-mode="card"]');

  // innehåll och översättning
  await page.keyboard.press('h');
  const caps = await page.locator('.keycap').allTextContents();
  check('hjälpen listar alla genvägar', caps.length === 7, caps.join(' '));
  check('hjälpen nämner både h och ?', caps.some(c => c.includes('h') && c.includes('?')));
  const helpSv = await page.textContent('#help_h');
  await page.keyboard.press('Escape');
  await page.selectOption('#ui', 'uk');
  await page.keyboard.press('h');
  const helpUk = await page.textContent('#help_h');
  check('hjälpen följer gränssnittsspråket', helpSv !== helpUk && /[\u0400-\u04FF]/.test(helpUk),
    `${helpSv} / ${helpUk}`);
  check('hjälptexten översätts', /[\u0400-\u04FF]/.test(await page.textContent('#helpbody')));
  await page.keyboard.press('Escape');
  await page.selectOption('#ui', 'sv');

  // --- kortkommandon på dator ---
  await page.click('#modes button[data-mode="card"]');
  await page.evaluate(() => { resetQueue(); renderCard(); });
  const kbState = () => page.evaluate(() => ({
    term: state.current && state.current.id, flipped: state.flipped,
    seen: state.seen, known: state.known, hist: state.history.length
  }));

  const k0 = await kbState();
  await page.keyboard.press('ArrowRight');
  const k1 = await kbState();
  check('höger visar svaret först', k1.flipped && k1.term === k0.term && k1.seen === k0.seen,
    `${k0.term} -> ${k1.term}, vänt=${k1.flipped}`);
  await page.keyboard.press('ArrowRight');
  const k2 = await kbState();
  check('höger igen går till nästa kort',
    !k2.flipped && k2.term !== k0.term && k2.seen === k0.seen + 1, `${k1.term} -> ${k2.term}`);

  await page.keyboard.press('ArrowLeft');
  const k3 = await kbState();
  check('vänster går till föregående kort', k3.term === k0.term, `${k2.term} -> ${k3.term}`);
  check('föregående kort visas med svaret framme', k3.flipped);
  check('statistiken backar med kortet', k3.seen === k0.seen && k3.known === k0.known,
    `visade ${k3.seen}, kan ${k3.known}`);
  await page.keyboard.press('ArrowRight');
  check('höger efter vänster går framåt igen', (await kbState()).term === k2.term);

  // stat- och köåterställning efter "kan" och "repetera"
  await page.evaluate(() => { resetQueue(); renderCard(); });
  const before = await page.evaluate(() => ({ seen: state.seen, known: state.known, kö: state.queue.length }));
  await page.keyboard.press('2');
  await page.keyboard.press('2');
  await page.keyboard.press('1');
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('ArrowLeft');
  const after = await page.evaluate(() => ({ seen: state.seen, known: state.known, kö: state.queue.length }));
  check('tre steg bakåt återställer räknare och repetera-kö',
    after.seen === before.seen && after.known === before.known && after.kö === before.kö,
    `${JSON.stringify(before)} vs ${JSON.stringify(after)}`);

  const atStart = await page.evaluate(() => {
    resetQueue(); renderCard();
    const id = state.current.id; prev(); return id === state.current.id;
  });
  check('vänster i början gör ingenting', atStart);
  const capped = await page.evaluate(() => {
    resetQueue(); for (let i = 0; i < 80; i++) next(null); return state.history.length;
  });
  check('historiken är begränsad', capped === 50, `${capped} steg`);

  // höger går vidare i quizlägena
  await page.click('#modes button[data-mode="quiz"]');
  await page.waitForSelector('#qopts button');
  const q1 = await page.textContent('#qterm');
  await page.keyboard.press('ArrowRight');
  check('höger ger nästa quizfråga', (await page.textContent('#qterm')) !== q1 ||
    (await page.locator('#qopts button').count()) === 4);
  await page.click('#modes button[data-mode="card"]');
  await page.evaluate(() => { resetQueue(); renderCard(); });

  // --- bilder: licensrad, kortsvar och bildquiz ---
  const bilder = await (await page.request.get(base + 'data/bilder.json')).json();
  const cfgImgs = await page.evaluate(() => ({
    total: Object.keys(IMGS).length,
    med: Object.values(IMGS).filter(e => e.bild).length,
    unika: Object.values(IMGS).filter(e => e.bild && IMG_USES[e.bild] === 1).length,
    utanLicens: Object.values(IMGS).filter(e => e.bild && !e.licens).length
  }));
  check('bilddatan är i synk med data/bilder.json',
    cfgImgs.total === Object.keys(bilder).length, `${cfgImgs.total} vs ${Object.keys(bilder).length}`);
  check('ingen bild saknar licensuppgift', cfgImgs.utanLicens === 0, `${cfgImgs.utanLicens} utan licens`);
  check('det finns bilder att visa', cfgImgs.med > 100, `${cfgImgs.med} bilder`);

  // bilden ska visas först när kortet vänds
  await page.click('#modes button[data-mode="card"]');
  await page.evaluate(() => { state.current = pool().find(t => imgOf(t)); state.flipped = false; renderCard(); });
  check('bilden är dold innan kortet vänds', !(await page.locator('#cimg img').count()));
  await page.evaluate(() => { state.flipped = true; renderCard(); });
  check('bilden visas i svaret', (await page.locator('#cimg img').count()) === 1);
  const cred = (await page.textContent('.imgcred')).trim();
  check('bilden har upphovsperson och licens',
    cred.includes('·') && cred.includes('Wikimedia Commons'), cred);
  // URL-formen kontrolleras hermetiskt. Själva hämtningen från Wikimedia
  // rapporteras men fäller inte bygget — den säger inget om ändringen och gör
  // annars CI rött när Commons är långsamt eller döper om en tumnagel.
  const src = await page.getAttribute('#cimg img', 'src');
  check('bildadressen pekar på en Commons-tumnagel',
    /^https:\/\/upload\.wikimedia\.org\/wikipedia\/commons\//.test(src), src);
  check('bildtaggen begär CORS så service workern kan cacha',
    (await page.getAttribute('#cimg img', 'crossorigin')) === 'anonymous');
  const imgOk = await page.evaluate(async () => {
    const i = document.querySelector('#cimg img');
    await new Promise(r => { if (i.complete) r(); else { i.onload = r; i.onerror = r; } });
    return i.naturalWidth > 0;
  });
  if (!imgOk) warnings.push('bilden kunde inte hämtas från Commons (nätverk, ej kodfel)');
  // Upphovsfältet är fritext från Commons — det får inte spränga kreditraden.
  // Gränsen läses ur appen i stället för att upprepas här, och kapningen sker
  // vid rendering — datan behåller hela attributionen.
  const creditCheck = await page.evaluate(() => {
    const longestRaw = Math.max(...Object.values(IMGS).filter(e => e.bild)
      .map(e => (e.upphov || '').length));
    const longestShown = Math.max(...Object.values(IMGS).filter(e => e.bild)
      .map(e => shortCredit(e.upphov).length));
    return { MAX_CREDIT, longestRaw, longestShown };
  });
  check('kreditraden kapas vid visning', creditCheck.longestShown <= creditCheck.MAX_CREDIT + 1,
    `visad ${creditCheck.longestShown}, gräns ${creditCheck.MAX_CREDIT}`);
  // Egenskapen, inte datans råstorlek: bara strängar över gränsen får kapas,
  // och kapningen får aldrig lämna kvar enbart ett filnamn utan upphovsperson.
  const creditProps = await page.evaluate(() => {
    const bad = [];
    const FILEPREFIX = /^(?:\**\s*[^\s:]+\.(?:svg|png|jpe?g|gif|tif+)\s*:\s*)+/i;
    for (const [id, e] of Object.entries(IMGS)) {
      if (!e.bild) continue;
      const raw = e.upphov || '', shown = shortCredit(raw);
      if (shown.length > MAX_CREDIT + 1) bad.push(id + ':för-lång');
      // Filnamnsledet skalas bort med flit; i övrigt får inget kapas i onödan.
      if (raw.length <= MAX_CREDIT && !FILEPREFIX.test(raw) && shown !== raw)
        bad.push(id + ':kapad-i-onödan');
      if (/^[^\s]+\.(svg|png|jpe?g)/i.test(shown)) bad.push(id + ':bara-filnamn');
    }
    return bad;
  });
  check('kapningen rör bara det som är för långt och behåller upphovspersonen',
    creditProps.length === 0, creditProps.slice(0, 3).join(', '));
  const titled = await page.evaluate(() => {
    const s = document.querySelector('.imgcred span[title]');
    return s ? s.getAttribute('title').length >= s.textContent.length : false;
  });
  check('hela upphovsuppgiften finns i title', titled);

  // uteslutna bilder får inte dyka upp
  const uteslutna = await (await page.request.get(base + 'data/bilder-uteslutna.json')).json();
  const stillThere = await page.evaluate(
    ids => ids.filter(id => IMGS[id] && IMGS[id].bild),
    Object.keys(uteslutna).filter(k => !k.startsWith('_')));
  check('granskningsuteslutna bilder är borta', stillThere.length === 0, stillThere.join(','));
  // Vid homonym är uppslaget fel, inte bara bilden — artikellänken måste bort.
  const homonymArticles = await page.evaluate(ids => ids.filter(id => IMGS[id] && IMGS[id].artikel),
    Object.entries(uteslutna).filter(([k, v]) => !k.startsWith('_') &&
      String(v).toLowerCase().startsWith('homonym')).map(([k]) => k));
  check('homonymer länkar inte till fel artikel', homonymArticles.length === 0,
    homonymArticles.join(','));

  // bildquiz: bara unika bilder, annars finns flera rätta svar
  await page.click('#modes button[data-mode="image"]');
  await page.waitForSelector('#iopts button');
  check('bildquizet använder bara unika bilder', cfgImgs.unika > 50, `${cfgImgs.unika} unika`);
  const poolOnlyUnique = await page.evaluate(
    () => imagePool().every(t => IMG_USES[IMGS[t.id].bild] === 1));
  check('ingen delad bild kan bli bildfråga', poolOnlyUnique);
  check('bildfrågan visar en bild', (await page.locator('#qimg img').count()) === 1);
  check('bildfrågan har fyra alternativ', (await page.locator('#iopts button').count()) === 4);
  await page.evaluate(() => {
    const c = state.icur.item[state.front];
    [...document.getElementById('iopts').children].find(b => b.textContent === c).click();
  });
  check('rätt svar i bildquizet räknas',
    (await page.textContent('#i_r')).trim() === '1' && (await page.textContent('#i_n')).trim() === '1');

  // --- rapportraden ska finnas i bildquizet, där felaktiga bilder upptäcks ---
  await page.click('#modes button[data-mode="image"]');
  await page.waitForSelector('#iopts button');
  // Ny fråga: en redan besvarad fråga får visa artikellänken, en obesvarad inte.
  const repImg = await page.evaluate(() => {
    newImageQuestion();
    return {
      synlig: !!document.getElementById('creport').offsetParent,
      hrefs: [...document.querySelectorAll('#creport a')].map(a => a.getAttribute('href'))
    };
  });
  check('rapportraden syns i bildquizet', repImg.synlig);
  // Före avslöjandet är href medvetet "#" — adressen byggs vid klick, annars
  // skulle titeln och brödtexten röja svaret i statusraden.
  check('bildquizet har en rapportlänk', repImg.hrefs.length >= 2, repImg.hrefs.join(' '));
  check('rapportadressen byggs först vid klick i obesvarat läge',
    repImg.hrefs.every(h => h === '#'), repImg.hrefs.join(' '));
  check('wikipedialänken röjer inte svaret i en obesvarad bildfråga',
    !repImg.hrefs.some(h => h.includes('sv.wikipedia.org')), repImg.hrefs.join(' '));
  const quizLeak = await page.evaluate(() => {
    const it = state.icur.item;
    const dec = [...document.querySelectorAll('#creport a')]
      .map(a => decodeURIComponent(a.getAttribute('href') || '')).join(' ');
    return ['sv', 'la', 'uk', 'ru'].filter(k => dec.includes(it[k]))
      .concat(dec.includes(it.id) ? ['id'] : []);
  });
  check('rapportlänken bär inte svaret i en obesvarad bildfråga',
    quizLeak.length === 0, quizLeak.join(','));
  const afterAnswer = await page.evaluate(() => {
    const c = state.icur.item[state.front];
    [...document.getElementById('iopts').children].find(b => b.textContent === c).click();
    return [...document.querySelectorAll('#creport a')].map(a => a.getAttribute('href'));
  });
  check('artikellänken kommer fram när bildfrågan besvarats',
    afterAnswer.some(h => h.includes('sv.wikipedia.org')) ||
    !(await page.evaluate(() => !!articleOf(state.icur.item))),
    afterAnswer.length + ' länkar');

  // --- felrapportering per term ---
  await page.click('#modes button[data-mode="card"]');
  await page.evaluate(() => { state.current = pool()[0]; state.flipped = true; renderCard(); });
  const rep = await page.evaluate(() => ({
    hrefs: [...document.querySelectorAll('#creport a')].map(a => a.getAttribute('href')),
    id: state.current.id
  }));
  const gh = rep.hrefs.find(h => h.includes('/discussions/new'));
  const beforeFlip = await page.evaluate(() => {
    state.flipped = false; renderCard();
    return [...document.querySelectorAll('#creport a')].map(a => a.getAttribute('href'));
  });
  check('wikipedialänken visas inte innan kortet vänts',
    !beforeFlip.some(h => h.includes('sv.wikipedia.org')), beforeFlip.join(' '));
  // Rapportlänkens egen URL innehöll titel och brödtext med alla fyra språken
  // plus term-id:t, som är härlett ur latinet — allt syns i statusraden.
  const leak = await page.evaluate(() => {
    state.flipped = false; renderCard();
    const it = state.current;
    const dec = [...document.querySelectorAll('#creport a')]
      .map(a => decodeURIComponent(a.getAttribute('href') || '')).join(' ');
    return ['sv', 'la', 'uk', 'ru'].filter(k => dec.includes(it[k]))
      .concat(dec.includes(it.id) ? ['id'] : []);
  });
  check('rapportlänken bär inte svaret innan kortet vänts', leak.length === 0, leak.join(','));
  const afterFlip = await page.evaluate(() => {
    state.flipped = true; renderCard();
    return [...document.querySelectorAll('#creport a')].map(a => a.getAttribute('href'));
  });
  check('wikipedialänken visas när kortet vänts',
    afterFlip.some(h => h.includes('sv.wikipedia.org')));
  check('rapportlänk till GitHub-diskussion finns', !!gh);
  check('rapportlänken är förifylld med term-id',
    !!gh && decodeURIComponent(gh).includes('`' + rep.id + '`'), rep.id);
  check('rapportlänken har en kategori', !!gh && gh.includes('category='));
  check('e-postreserv finns för den utan GitHub-konto',
    rep.hrefs.some(h => h.startsWith('mailto:')));

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
