#!/usr/bin/env python3
"""Bygg ett Anki-deck (.apkg) med fyra språk från anatomi-termer.json.

Kortmodellen har ett korttyp per frågespråk (svenska, latin, ukrainska, ryska)
och varje kategori blir ett eget underdeck. Guid:n härleds från fältet ``id``
så att en omgenerering uppdaterar befintliga kort i stället för att dubblera dem.

Användning:
    python tools/build_deck.py [--json data/anatomi-termer.json]
                               [--out data/anatomi-4sprak.apkg]
"""

import argparse
import hashlib
import json
import pathlib
import sys

import genanki

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_JSON = ROOT / "data" / "anatomi-termer.json"
DEFAULT_OUT = ROOT / "data" / "anatomi-4sprak.apkg"
LANGS_PATH = ROOT / "data" / "sprak.json"

DECK_NAME = "Anatomi 4 språk"
# Stabila id:n – ändra dem inte, annars skapas nya decks/modeller vid import.
MODEL_ID = 1607392913
DECK_ID_SEED = "anatomi-4sprak"

def load_langs():
    """Språkuppsättningen kommer från data/sprak.json, samma fil som webbappen
    använder. Lägg till ett språk där och både appen och decket följer med."""
    langs = json.loads(LANGS_PATH.read_text(encoding="utf-8"))
    # ankifalt/ankidef är Ankis fältnamn och måste vara stabila — byter de namn
    # bryts befintliga användares kort vid en ny import. Därför står de
    # uttryckligen i konfigurationen i stället för att härledas ur visningsnamnet.
    term = [(k, v["ankifalt"], v["namn"].lower()) for k, v in langs.items() if v.get("term")]
    defs = [(k, v["ankidef"]) for k, v in langs.items() if v.get("forklaring")]
    return term, defs


TERM_LANGS, DEF_LANGS = load_langs()

# Anki kopplar notinnehåll till fält via ordningsnummer, inte namn, och MODEL_ID
# är pinnad. Om fältordningen ändras hamnar därför latin i svenskfältet på alla
# befintliga användares kort vid nästa import. Ordningen får bara växa i slutet.
FIELD_ORDER = ["Svenska", "Latin", "Ukrainska", "Ryska",
               "DefSv", "DefUk", "DefRu", "Kategori"]


def stable_field_order(fields):
    """Lås de åtta ursprungliga fälten vid sina ordningsnummer.

    Ett nytt språk ger både ett term- och ett förklaringsfält, som naturligt
    skulle hamna mitt i listan och putta DefSv från plats 4 till 5. Eftersom
    Anki kopplar notinnehåll till fält via ordningsnummer, och MODEL_ID är
    pinnad, skulle det flytta latin in i svenskfältet på alla befintliga kort
    vid nästa import. Nya fält läggs därför alltid sist.
    """
    missing = [f for f in FIELD_ORDER if f not in fields]
    if missing:
        raise SystemExit(
            f"data/sprak.json saknar fälten {missing}, som är låsta av MODEL_ID "
            f"{MODEL_ID}. Att ta bort ett språk kräver ett nytt MODEL_ID och en "
            "ny import hos alla användare."
        )
    return FIELD_ORDER + [f for f in fields if f not in FIELD_ORDER]

# Fältnamnen i Anki: ett per termspråk, ett per förklaringsspråk, plus kategori.
FIELDS = stable_field_order([field for _, field, _ in TERM_LANGS]
                            + [field for _, field in DEF_LANGS]
                            + ["Kategori"])

CSS = """
.card {
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 20px;
  text-align: center;
  color: #141a20;
  background-color: #f6f7f9;
}
.q { font-size: 28px; font-weight: 600; }
.qlang, .cat { font-size: 12px; color: #5b6673; text-transform: uppercase; letter-spacing: .08em; }
.answers { text-align: left; display: inline-block; margin-top: 8px; }
.answers div { padding: 2px 0; }
.tag { font-size: 12px; color: #5b6673; text-transform: uppercase; margin-right: 6px; }
.def { font-size: 15px; color: #5b6673; margin-top: 10px; }
"""

# Ett korttyp per frågespråk: (kortnamn, frågefält, etikett, svarsfält i ordning)
CARD_SPECS = [
    (f"{field} → övriga", field, label,
     [other for _, other, _ in TERM_LANGS if other != field])
    for _, field, label in TERM_LANGS
]

def _qfmt(qfield, qlang):
    return (
        f'<div class="qlang">{qlang}</div>\n'
        f'<div class="q">{{{{{qfield}}}}}</div>'
    )


def _afmt(qfield, qlang, answers):
    rows = "\n".join(
        f'  <div><span class="tag">{f}</span>{{{{{f}}}}}</div>' for f in answers
    )
    defs = "\n".join(
        f'<div class="def">{{{{{field}}}}}</div>' for _, field in DEF_LANGS
    )
    return (
        f'{_qfmt(qfield, qlang)}\n'
        "<hr id=answer>\n"
        f'<div class="answers">\n{rows}\n</div>\n'
        f'{defs}\n'
        '<div class="cat">{{Kategori}}</div>'
    )


def build_model():
    templates = [
        {
            "name": name,
            "qfmt": _qfmt(qfield, qlang),
            "afmt": _afmt(qfield, qlang, answers),
        }
        for name, qfield, qlang, answers in CARD_SPECS
    ]
    return genanki.Model(
        MODEL_ID,
        "Anatomi 4 språk",
        fields=[{"name": f} for f in FIELDS],
        templates=templates,
        css=CSS,
    )


def stable_id(*parts):
    """Deterministiskt 31-bitars id ur en sträng (Anki vill ha positiva int)."""
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) & 0x7FFFFFFF


class StableNote(genanki.Note):
    """Note vars guid härleds ur term-id:t i JSON, inte ur fältinnehållet."""

    def __init__(self, term_id, **kwargs):
        super().__init__(**kwargs)
        self._stable_guid = genanki.guid_for(DECK_ID_SEED, term_id)

    @property
    def guid(self):
        return self._stable_guid

    @guid.setter
    def guid(self, value):  # genanki.Note.__init__ sätter guid; ignorera det
        pass


# Fältnamn -> hur värdet plockas ur en term.
FIELD_SOURCE = {}
for _code, _field, _ in TERM_LANGS:
    FIELD_SOURCE[_field] = ("term", _code)
for _code, _field in DEF_LANGS:
    FIELD_SOURCE[_field] = ("def", "def_" + _code)


def field_value(term, name, cat):
    if name == "Kategori":
        return cat
    kind, key = FIELD_SOURCE[name]
    return term[key] if kind == "term" else term.get(key, "")


def build(json_path, out_path):
    terms = json.loads(pathlib.Path(json_path).read_text(encoding="utf-8"))
    model = build_model()

    decks = {}
    for term in terms:
        cat = term["cat"]
        if cat not in decks:
            full_name = f"{DECK_NAME}::{cat}"
            decks[cat] = genanki.Deck(stable_id(DECK_ID_SEED, cat), full_name)
        note = StableNote(
            term["id"],
            model=model,
            fields=[field_value(term, name, cat) for name in FIELDS],
            tags=["anatomi"],
        )
        decks[cat].add_note(note)

    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    package = genanki.Package(sorted(decks.values(), key=lambda d: d.name))
    package.write_to_file(str(out_path))

    print(f"{len(terms)} termer i {len(decks)} underdeck, "
          f"{len(TERM_LANGS)} korttyper -> {out_path}")
    for cat in sorted(decks):
        print(f"  {len(decks[cat].notes):3d}  {cat}")
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=str(DEFAULT_JSON))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    build(args.json, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
