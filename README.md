# Anatomi 4 språk

Flashcards för grundläggande anatomi, fysiologi och medicinsk terminologi på
**svenska, latin, ukrainska och ryska** — 423 termer med korta förklaringar på
svenska, ukrainska och ryska.

Materialet är tänkt som stöd för elever som läser **Anatomi och fysiologi 1** på
vård- och omsorgsprogrammet och som har ukrainska eller ryska som starkaste språk;
termurvalet följer kursens centrala innehåll om kroppens uppbyggnad, organsystemens
funktion och vanlig medicinsk terminologi.

## Innehåll

| Fil | Beskrivning |
| --- | --- |
| `index.html` | Fristående webbapp med flashcards, quiz och söklista. Allt ligger i en enda fil, inga beroenden. |
| `data/anatomi-termer.json` | Termdatan. Fält: `id`, `cat`, `sv`, `la`, `uk`, `ru`, `def_sv`, `def_uk`, `def_ru`, `n`. |
| `data/anatomi-4sprak.apkg` | Anki-deck genererat från JSON-filen. |
| `tools/build_deck.py` | Bygger om `.apkg` från JSON med `genanki`. |
| `tools/check_data.py` | Kontrollerar termdatans invarianter och att `index.html` är i synk med JSON-filen. |
| `tools/verify_app.mjs` | Rökprov som kör webbappen i en headless-webbläsare (Playwright). |
| `tests/` | Pytest-tester för `check_data.py`. |
| `manifest.webmanifest`, `sw.js` | Gör sajten installerbar och användbar offline. |

Webbappen kan visa frågan på vilket som helst av de fyra språken, med valfria
svarsspråk, förklaring på svenska/ukrainska/ryska och filtrering per kategori.
Gränssnittet finns på svenska, ukrainska och ryska.

## Termer per kategori

| Kategori | Antal |
| --- | ---: |
| Skelettet | 46 |
| Kroppens organisation och riktningstermer | 40 |
| Medicinsk terminologi | 35 |
| Leder och muskler | 34 |
| Matsmältningsorganen | 33 |
| Hjärta och blodkärl | 32 |
| Nervsystemet | 30 |
| Blod och immunförsvar | 22 |
| Sinnesorganen | 22 |
| Andningsorganen | 21 |
| Cellen och vävnader | 20 |
| Reproduktionsorganen | 20 |
| Vanliga kliniska termer | 20 |
| Urinorganen | 17 |
| Endokrina systemet | 16 |
| Huden | 15 |
| **Totalt** | **423** |

## Importera decket i Anki

1. Ladda ner `data/anatomi-4sprak.apkg` (länken finns också i sidfoten på sajten).
2. Öppna Anki på datorn och välj **Arkiv → Importera…** (eller dra filen till Anki-fönstret).
   I AnkiMobile/AnkiDroid räcker det att öppna filen med Anki.
3. Decket heter *Anatomi 4 språk* och innehåller ett underdeck per kategori.

Varje term ger fyra kort — ett per frågespråk (svenska, latin, ukrainska, ryska) —
alltså 1 692 kort totalt. Vill du bara öva ett håll kan du stänga av de övriga
korttyperna under **Verktyg → Hantera korttyper**.

Korten har stabila guid:n som härleds ur `id`-fältet i JSON-filen. Importerar du en
nyare version av decket uppdateras därför befintliga kort i stället för att dubbleras,
och din inlärningsstatistik behålls.

## Bygga om decket

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python tools/build_deck.py
```

Skriptet läser `data/anatomi-termer.json` och skriver `data/anatomi-4sprak.apkg`.
Andra sökvägar går att ange med `--json` och `--out`.

### Ändra en term

Termdatan finns på **två** ställen: inbakad i `index.html` (webbappen är en enda fil
utan beroenden och hämtar ingenting) och i `data/anatomi-termer.json` (som decket byggs
från). Ändrar du en term måste båda uppdateras. Kontrollera med:

```bash
python tools/check_data.py
```

Skriptet verifierar att `id` och `n` är unika, att alla fält är ifyllda och att
`index.html` och JSON-filen innehåller exakt samma data. Samma kontroll körs i CI och
stoppar bygget om filerna glidit isär.

Vid push till `main` som ändrar termdatan byggs decket automatiskt om av GitHub Actions
(`.github/workflows/deck.yml`), den nya `.apkg`-filen committas och sajten deployas om.
Eftersom genanki skriver tidsstämplar i `.apkg`-filen är utdatan inte byte-identisk
mellan körningar; workflowet jämför därför en checksumma över källorna
(`data/deck-source.sha256`) i stället för själva deckfilen, så att oförändrat innehåll
inte ger en ny binär commit vid varje körning.

## Offline och installation

Sajten registrerar en service worker (endast över `https:`) som precachar skalet —
sidan och manifestet — och cachar övriga filer, som Anki-decket, i takt med att de
efterfrågas. Svaret kommer alltid från cachen först, medan en ny version hämtas i
bakgrunden och används vid nästa besök. Efter första besöket fungerar appen utan
nätverk. Behöver du tvinga fram en total omladdning för alla besökare, höj
`CACHE`-nyckeln i `sw.js`.

Manifestet saknar ikoner. Sajten går att lägga till på hemskärmen i Safari på iOS,
men Chrome och Edge kräver ikoner på 192×192 och 512×512 px innan de erbjuder
"installera app" — lägg till en `icons`-lista i `manifest.webmanifest` om den
funktionen behövs.

## CI

`.github/workflows/ci.yml` körs vid varje push och pull request:

- `tools/check_data.py` — termdatans invarianter och synken mot `index.html`
- `pytest tests` — tester för kontrollskriptet
- ett rökbygge av `.apkg` och en syntaxkontroll av `sw.js`
- `tools/verify_app.mjs` — serverar katalogen över http, startar webbappen i headless
  Chromium och kör 24 kontroller: kortvändning, byte av frågespråk till latin, ett rätt
  quizsvar som ska räknas som rätt, sökning på svenska, ukrainska och ryska förklaringar
  med förväntat radantal, nedladdningslänken, manifestet och att konsolen är fri från fel.
  Sökord och antal härleds ur datan, så en ny eller ändrad term fäller inte bygget

Kör detsamma lokalt:

```bash
pip install -r requirements-dev.txt
python tools/check_data.py && python -m pytest tests -q
npm install playwright && npx playwright install chromium
node tools/verify_app.mjs .
```

## Licens

Termdatan och koden får användas fritt i undervisning.
