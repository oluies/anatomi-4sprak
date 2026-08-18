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

Vid push till `main` som ändrar `data/anatomi-termer.json` byggs decket automatiskt om
av GitHub Actions (`.github/workflows/deck.yml`), och den nya `.apkg`-filen committas.

## Offline och installation

Sajten registrerar en service worker (endast över `https:`) som cachar sidan,
manifestet och filerna i `data/`. Efter första besöket fungerar appen utan nätverk,
och den kan installeras som app från webbläsarens meny. Höj cache-nyckeln i `sw.js`
när innehållet ändras.

## Licens

Termdatan och koden får användas fritt i undervisning.
