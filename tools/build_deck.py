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

DECK_NAME = "Anatomi 4 språk"
# Stabila id:n – ändra dem inte, annars skapas nya decks/modeller vid import.
MODEL_ID = 1607392913
DECK_ID_SEED = "anatomi-4sprak"

FIELDS = [
    "Svenska",
    "Latin",
    "Ukrainska",
    "Ryska",
    "DefSv",
    "DefUk",
    "DefRu",
    "Kategori",
]

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

# (kortnamn, frågefält, etikett för frågespråket, svarsfält i ordning)
CARD_SPECS = [
    ("Svenska → övriga", "Svenska", "svenska", ["Latin", "Ukrainska", "Ryska"]),
    ("Latin → övriga", "Latin", "latin", ["Svenska", "Ukrainska", "Ryska"]),
    ("Ukrainska → övriga", "Ukrainska", "українська", ["Svenska", "Latin", "Ryska"]),
    ("Ryska → övriga", "Ryska", "русский", ["Svenska", "Latin", "Ukrainska"]),
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
    return (
        f'{_qfmt(qfield, qlang)}\n'
        "<hr id=answer>\n"
        f'<div class="answers">\n{rows}\n</div>\n'
        '<div class="def">{{DefSv}}</div>\n'
        '<div class="def">{{DefUk}}</div>\n'
        '<div class="def">{{DefRu}}</div>\n'
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
            fields=[
                term["sv"],
                term["la"],
                term["uk"],
                term["ru"],
                term.get("def_sv", ""),
                term.get("def_uk", ""),
                term.get("def_ru", ""),
                cat,
            ],
            tags=["anatomi"],
        )
        decks[cat].add_note(note)

    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    package = genanki.Package(sorted(decks.values(), key=lambda d: d.name))
    package.write_to_file(str(out_path))

    print(f"{len(terms)} termer i {len(decks)} underdeck -> {out_path}")
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
