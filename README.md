# Anatomi 4 språk

Flashcards för grundläggande anatomi, fysiologi och medicinsk terminologi på
**svenska, latin, ukrainska och ryska** — 438 termer med korta förklaringar på
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
| `data/kategorier.json` | Kategorinamnen översatta till ukrainska, ryska och engelska. |
| `data/bilder.json` | Bild och artikellänk per term, hämtade från svenskspråkiga Wikipedia, med licens och upphovsperson. |
| `data/bilder-uteslutna.json` | Term-id vars automatiskt valda bild underkänts vid granskning, med skäl. |
| `tools/fetch_images.py` | Slår upp bilderna mot Wikipedias API och skriver `bilder.json`. Körs för hand. `--only <kategori>` uppdaterar bara den kategorin och lämnar övriga poster orörda. |
| `data/sprak.json` | Språkuppsättningen: vilka språk som är termspråk, har förklaringar, går att välja som gränssnitt, och vad fälten heter i Anki. |
| `data/anatomi-4sprak.apkg` | Anki-deck genererat från JSON-filen. |
| `tools/build_deck.py` | Bygger om `.apkg` från JSON med `genanki`. |
| `tools/sync_html_data.py` | Skriver om det inbakade `DATA`-blocket i `index.html` från JSON-filen och numrerar om `n`. |
| `tools/check_data.py` | Kontrollerar termdatans invarianter och att `index.html` är i synk med JSON-filen. |
| `tools/verify_app.mjs` | Rökprov som kör webbappen i en headless-webbläsare (Playwright). |
| `tests/` | Pytest-tester för `check_data.py`. |
| `manifest.webmanifest`, `sw.js` | Gör sajten installerbar och användbar offline. |

Webbappen kan visa frågan på vilket som helst av de fyra språken, med valfria
svarsspråk, förklaring på svenska/ukrainska/ryska och filtrering per kategori.
Gränssnittet finns på svenska, ukrainska och ryska.

På dator finns kortkommandon i flashcard-läget: **→** visar först svaret och går
vid nästa tryck vidare till nästa kort, **←** går tillbaka till föregående kort
(med svaret framme, så pilarna blir symmetriska), **mellanslag** vänder kortet,
**1** lägger kortet sist i kön för repetition och **2** markerar det som kunnigt.
Att gå bakåt återställer även räknarna och repetera-kön, så statistiken stämmer.
I quizlägena går **→** till nästa fråga. **h** eller **?** öppnar en hjälpruta som
beskriver lägena, genvägarna och inställningarna på gränssnittets språk; **Esc**,
klick utanför rutan eller knappen **?** i sidhuvudet stänger den. Raden med genvägar
visas bara på enheter med tangentbord, medan **?**-knappen finns även på telefon.

Urvalsinställningarna — språk, svarsspråk och kategorier — går att fälla ihop och är
hopfällda från start på telefon, där de annars fyller nästan hela skärmen innan man ser
ett kort. Hopfällda ersätts de av en rad som visar vad som är valt.

## Termer per kategori

| Kategori | Antal |
| --- | ---: |
| Leder och muskler | 49 |
| Skelettet | 46 |
| Kroppens organisation och riktningstermer | 40 |
| Medicinsk terminologi | 35 |
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
| **Totalt** | **438** |

## Importera decket i Anki

1. Ladda ner `data/anatomi-4sprak.apkg` (länken finns också i sidfoten på sajten).
2. Öppna Anki på datorn och välj **Arkiv → Importera…** (eller dra filen till Anki-fönstret).
   I AnkiMobile/AnkiDroid räcker det att öppna filen med Anki.
3. Decket heter *Anatomi 4 språk* och innehåller ett underdeck per kategori.

Varje term ger fyra kort — ett per frågespråk (svenska, latin, ukrainska, ryska) —
alltså 1 752 kort totalt. Vill du bara öva ett håll kan du stänga av de övriga
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
utan beroenden och hämtar ingenting) och i `data/anatomi-termer.json`. JSON-filen är
källan — redigera den, lägg nya termer där de hör hemma i kategorin, och kör sedan:

```bash
python tools/sync_html_data.py   # skriver om DATA i index.html och numrerar om n
python tools/check_data.py       # kontrollerar invarianterna
```

Skriptet verifierar att `id` och `n` är unika, att alla fält är ifyllda, att
`index.html` och JSON-filen innehåller exakt samma data, och att en svensk term
inte upprepar sitt eget latinska namn i parentes — latinet har ett eget fält och
en dubblett avslöjar svaret när latin är svarsspråk. Svenska förklaringar i
parentes, som `anterior (främre)`, är avsiktliga och flaggas inte.

Termerna innehåller alltså inte sitt eget latin: `organsystem`, inte
`organsystem (systema organorum)`. Parentesen används bara till svenska
förklaringar (`kaudal (mot svansbenet)`) och till svenska synonymer där båda
formerna är svenska (`erytrocyt (röd blodkropp)`). Samma kontroll körs i CI och
stoppar bygget om filerna glidit isär.

### Lägga till ett språk

Språken är inte hårdkodade i appen. För att lägga till exempelvis polska (`pl`),
litauiska (`lt`), lettiska (`lv`) eller estniska (`et`):

1. Lägg in språket i `data/sprak.json`:

   ```json
   "pl": {"namn": "Polski", "term": true, "forklaring": true,
          "granssnitt": "Polski", "ankifalt": "Polska", "ankidef": "DefPl"}
   ```

   `term` gör språket valbart som fråge- och svarsspråk, `forklaring` ger det ett
   `def_pl`-fält, och `granssnitt` gör det valbart som gränssnittsspråk.
   `ankifalt`/`ankidef` är fältnamnen i Anki och måste vara stabila över tid —
   byter de namn bryts befintliga användares kort vid en ny import.

2. Lägg fälten `pl` och `def_pl` på **varje** term i `data/anatomi-termer.json`.
3. Översätt kategorinamnen i `data/kategorier.json`.
4. Vill du ha gränssnittet på språket: lägg till en `pl`-post i `I18N` i `index.html`.
   Utan den faller gränssnittet tillbaka på svenska, men termerna fungerar ändå.
5. Kör `python tools/sync_html_data.py`.

Sync-verktyget vägrar om någon term saknar det nya fältet, så du får veta direkt
om översättningen är ofullständig. Appen bygger språkväljare, svarschips, listkolumner
och sökning ur konfigurationen, och `build_deck.py` lägger automatiskt till ett
Anki-fält och en korttyp per nytt termspråk.

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
  Chromium och kör hela kontrollsviten: kortvändning, byte av frågespråk till latin, ett rätt
  quizsvar som ska räknas som rätt, sökning på svenska, ukrainska och ryska förklaringar
  med förväntat radantal, att svenska visas som svar för varje frågespråk, att panelen
  med urvalsinställningar fälls ihop och ut, nedladdningslänken, manifestet och att
  konsolen är fri från fel. Kontrollerna körs både i desktop- och telefonvy, och sökord
  och antal härleds ur datan så att en ny eller ändrad term inte fäller bygget

Kör detsamma lokalt:

```bash
pip install -r requirements-dev.txt
python tools/check_data.py && python -m pytest tests -q
npm install playwright && npx playwright install chromium
node tools/verify_app.mjs .
```

## Bilder

Drygt 250 termer har en bild från svenskspråkiga Wikipedia. Bilden visas i svaret på
flashcardet och i lägen *Bildquiz*, där man får se bilden och välja rätt term.

Bilderna **hotlänkas** från `upload.wikimedia.org` — de ligger inte i repot. Service
workern cachar dem efterhand, så en bild man sett en gång finns kvar offline. Varje
bild visas tillsammans med upphovsperson, licens och länk till filsidan på Commons;
en bild utan känd licens publiceras inte.

Bildquizet använder bara termer vars bild är **unik**. Wikipedias huvudbild är ofta
en översiktsillustration som delas av flera termer — samma njurdiagram gäller för
njure, njurbark, njurmärg och njurbäcken — och en delad bild skulle ge flera rätta
svar på samma fråga.

### Uppdatera bildurvalet

```bash
python tools/fetch_images.py          # skriver om data/bilder.json
python tools/sync_html_data.py        # bakar in det i index.html
```

Skriptet slår upp varje term på svenskspråkiga Wikipedia och tar artikelns huvudbild.
Det kontrollerar också mot Wikidata om artikeln har en anatomisk identifierare (FMA,
TA98, UBERON, MeSH) och **varnar** för dem som saknar den, eftersom det ofta är
homonymer: uppslaget på *atlas* gav titanen i grekisk mytologi, *falang* gav den
antika stridsformeringen och *lins* gav den optiska linsen. Varningen är avsiktligt
inte ett automatiskt bortval — flera korrekta artiklar (Bröstkorg, Penis, Förlossning)
saknar också identifierarna. Underkända bilder förs in i `data/bilder-uteslutna.json` och utesluts vid nästa
körning:

```json
"atlas": {"skal": "artikeln handlar om titanen", "artikel_ok": false}
```

`artikel_ok: false` betyder att uppslaget självt är fel, inte bara bilden — då tas
även artikellänken bort, annars skulle "Läs mer på Wikipedia" skicka eleven till
fel artikel. Avsikten deklareras alltså i stället för att läsas ut ur en fritext,
och formen kontrolleras av `sync_html_data.py`.

## Felrapportering

Varje kort har en rad med **Läs mer på Wikipedia**, **Rapportera fel i den här termen**
och **e-post**. Rapportlänken öppnar en förifylld
[GitHub-diskussion](https://github.com/oluies/anatomi-4sprak/discussions) med term-id,
kategori och alla fyra språken, så att det går att se exakt vilken term det gäller.
GitHub kräver inloggning för att skriva, därför finns e-postlänken som alternativ för
den som inte har ett konto.

## Besöksstatistik

Sajten räknar sidvisningar med [GoatCounter](https://www.goatcounter.com/) — ingen
kaka, ingen IP-lagring, inga personuppgifter, bara ett antal. Skriptet laddas bara
över `https:`, så lokala körningar och rökprovet i CI hamnar inte i statistiken, och
inte alls om besökaren skickar `Do Not Track` eller `Global Privacy Control`.

Kontokoden står som `CODE` i skriptblocket längst ned i `index.html`:

```js
var CODE = "anatomi-4sprak";
```

**Registrera koden innan det ger någon data**: skapa kontot på
[goatcounter.com](https://www.goatcounter.com/signup) med exakt det namnet, annars
går anropen till en adress som inte finns. Väljer du ett annat namn räcker det att
byta den raden. GoatCounter är gratis för icke-kommersiell användning och går även
att köra själv.

Statistiken kan göras publik i GoatCounters inställningar om du vill att andra ska
kunna se den.

## Licens och källor

Hela projektet — både termdatan och koden — är licensierat under
[Creative Commons Erkännande-DelaLika 4.0 Internationell (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/deed.sv).
Licenstexten finns i [`LICENSE`](LICENSE).

Det betyder att du fritt får kopiera, sprida och bearbeta materialet, även
kommersiellt, så länge du **anger källan** och sprider eventuella bearbetningar
under **samma licens**.

Termdatan är delvis baserad på artikeln
[Människans anatomi](https://sv.wikipedia.org/wiki/M%C3%A4nniskans_anatomi)
och närliggande artiklar på svenskspråkiga Wikipedia, som också är CC BY-SA 4.0.
Wikipedias upphovspersoner framgår av respektive artikels versionshistorik.

Skapad av [Örjan Lundberg](https://github.com/oluies).

Vill du stödja källan går det att
[donera till Wikimedia](https://donate.wikimedia.org/).
