// Rökprov för index.html i en headless-webbläsare.
// Vänder ett kort, byter frågespråk till latin, kör en quizfråga, söker i listan
// och kräver att konsolen är helt fri från fel och varningar.
// Körs i CI av .github/workflows/ci.yml. Lokalt: npm i playwright && node tools/verify_app.mjs index.html
import { chromium } from 'playwright';
import path from 'path';

const file = 'file://' + path.resolve(process.argv[2]);
const errors = [];
const browser = await chromium.launch();
const page = await browser.newPage();
page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`[${m.type()}] ${m.text()}`); });
page.on('pageerror', e => errors.push(`[pageerror] ${e.message}`));

await page.goto(file, { waitUntil: 'load' });

const results = {};

// --- 1. initial card render ---
results.total = (await page.textContent('#total')).trim();
const frontTerm = (await page.textContent('#fterm')).trim();
results.firstTerm = frontTerm;
results.answersHiddenBeforeFlip = (await page.getAttribute('#answers', 'class')).includes('hidden');

// --- 2. flip a card ---
await page.click('#card');
const cls = await page.getAttribute('#answers', 'class');
results.answersVisibleAfterFlip = !cls.includes('hidden');
results.answerRows = await page.locator('#answers .ans').count();
results.answerText = (await page.textContent('#answers')).replace(/\s+/g, ' ').trim().slice(0, 120);

// --- 3. switch question language to latin ---
await page.selectOption('#front', 'la');
results.frontLabelAfterSwitch = (await page.textContent('#flabel')).trim();
const latinTerm = (await page.textContent('#fterm')).trim();
results.latinTerm = latinTerm;
// confirm it really is the latin field for that term
const isLatin = await page.evaluate(t => DATA.some(d => d.la === t), latinTerm);
results.latinTermFoundInData = isLatin;

// --- 4. run one quiz question ---
await page.click('#modes button[data-mode="quiz"]');
await page.waitForSelector('#qopts button');
results.quizQuestion = (await page.textContent('#qterm')).trim();
results.quizOptionCount = await page.locator('#qopts button').count();
// find and click the correct option
const correct = await page.evaluate(() => {
  const q = document.getElementById('qterm').textContent.trim();
  const item = DATA.find(d => [d.sv, d.la, d.uk, d.ru].includes(q));
  return item ? [item.sv, item.la, item.uk, item.ru] : null;
});
const buttons = await page.locator('#qopts button').all();
let clicked = null;
for (const b of buttons) {
  const t = (await b.textContent()).trim();
  if (correct && correct.includes(t)) { await b.click(); clicked = t; break; }
}
if (!clicked) { await buttons[0].click(); clicked = '(gissning)'; }
results.quizAnswerClicked = clicked;
results.quizAsked = (await page.textContent('#q_n')).trim();
results.quizRight = (await page.textContent('#q_r')).trim();
await page.click('#qnext');
results.quizNextWorks = (await page.textContent('#qterm')).trim().length > 0;

// --- 5. list mode + search, and footer link ---
await page.click('#modes button[data-mode="list"]');
await page.fill('#search', 'cor');
results.listRowsForSearchCor = await page.locator('#tbl tbody tr').count();
results.apkgLink = await page.getAttribute('a[href="data/anatomi-4sprak.apkg"]', 'href');
results.apkgLinkText = (await page.textContent('a[href="data/anatomi-4sprak.apkg"]')).trim();
results.manifestLink = await page.getAttribute('link[rel="manifest"]', 'href');
// service worker must NOT register over file: protocol
results.swControllerOnFileProtocol = await page.evaluate(() => !!(navigator.serviceWorker && navigator.serviceWorker.controller));

await browser.close();
console.log(JSON.stringify(results, null, 2));
console.log('\nCONSOLE ERRORS/WARNINGS: ' + (errors.length ? '\n' + errors.join('\n') : 'none'));
process.exit(errors.length ? 1 : 0);
