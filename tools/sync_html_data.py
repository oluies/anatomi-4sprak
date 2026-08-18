#!/usr/bin/env python3
"""Skriv om DATA- och CATS-blocken i index.html från filerna i data/.

Webbappen är avsiktligt en enda fil utan beroenden och har därför termdatan
och kategoriöversättningarna inbakade. Filerna i data/ är källan; det här
skriptet håller kopiorna i synk så att tools/check_data.py alltid går igenom.
Numreringen (fältet n) sätts om till arrayens ordning, så en ny term kan
läggas in var som helst i JSON-filen.

Användning:
    python tools/sync_html_data.py            # skriv om index.html
    python tools/sync_html_data.py --check    # ändra inget, returnera 1 vid drift
"""

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "anatomi-termer.json"
CATS_PATH = ROOT / "data" / "kategorier.json"
LANGS_PATH = ROOT / "data" / "sprak.json"
IMGS_PATH = ROOT / "data" / "bilder.json"
EXCLUDE_PATH = ROOT / "data" / "bilder-uteslutna.json"
HTML_PATH = ROOT / "index.html"

# (variabelnamn i index.html, öppnande tecken)
BLOCKS = [("const DATA = ", "["), ("const CATS = ", "{"), ("const IMGS = ", "{"),
          ("const LANGS = ", "{"), ("const DEFLANGS = ", "{"), ("const UILANGS = ", "{")]


def dump(terms):
    """Samma kompakta serialisering som index.html redan använder."""
    return json.dumps(terms, ensure_ascii=False, separators=(",", ":"))


def renumber(terms):
    for i, term in enumerate(terms, start=1):
        term["n"] = i
    return terms


def replace_block(html, marker, opener, value):
    """Byt ut ett `const X = ...;`-block i index.html mot value."""
    start = html.find(marker)
    if start == -1:
        raise SystemExit(f"index.html: hittade ingen '{marker}' -rad")
    closer = {"[": "];", "{": "};"}[opener]
    try:
        begin = html.index(opener, start)
        end = html.index(closer, begin)
    except ValueError:
        raise SystemExit(f"index.html: '{marker}' saknar avslutande '{closer}'")
    return html[:begin] + value + html[end + 1:], html[begin:end + 1] == value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="rapportera drift utan att skriva om något")
    args = parser.parse_args(argv)

    terms = renumber(json.loads(JSON_PATH.read_text(encoding="utf-8")))
    cats = json.loads(CATS_PATH.read_text(encoding="utf-8"))

    missing = sorted({t["cat"] for t in terms} - set(cats))
    if missing:
        raise SystemExit(f"{CATS_PATH.name}: saknar översättning för {missing}")
    unused = sorted(set(cats) - {t["cat"] for t in terms})
    if unused:
        # Varning, inte fel: en kategori kan bli tom en stund under redigering,
        # och --check kör i CI:s validate-jobb där ett stopp vore oproportionerligt.
        print(f"varning: {CATS_PATH.name} har översättningar som ingen term använder: {unused}",
              file=sys.stderr)

    langs = json.loads(LANGS_PATH.read_text(encoding="utf-8"))
    term_langs = {k: v["namn"] for k, v in langs.items() if v.get("term")}
    def_langs = {k: v["namn"] for k, v in langs.items() if v.get("forklaring")}
    def_langs["none"] = "—"
    ui_langs = {k: v["granssnitt"] for k, v in langs.items() if v.get("granssnitt")}

    for code in term_langs:
        missing_field = [t["id"] for t in terms if not str(t.get(code, "")).strip()]
        if missing_field:
            raise SystemExit(
                f"{JSON_PATH.name}: {len(missing_field)} termer saknar fältet '{code}' "
                f"(t.ex. {missing_field[:3]})")
    for code in def_langs:
        if code == "none":
            continue
        field = "def_" + code
        missing_def = [t["id"] for t in terms if not str(t.get(field, "")).strip()]
        if missing_def:
            raise SystemExit(
                f"{JSON_PATH.name}: {len(missing_def)} termer saknar fältet '{field}' "
                f"(t.ex. {missing_def[:3]})")

    html = HTML_PATH.read_text(encoding="utf-8")
    in_sync = True
    imgs = json.loads(IMGS_PATH.read_text(encoding="utf-8"))
    excluded = json.loads(EXCLUDE_PATH.read_text(encoding="utf-8"))
    for term_id, rule in excluded.items():
        if term_id.startswith("_"):
            continue
        if not isinstance(rule, dict) or not isinstance(rule.get("artikel_ok"), bool) \
                or not str(rule.get("skal", "")).strip():
            raise SystemExit(
                f"{EXCLUDE_PATH.name}: {term_id} måste vara "
                '{"skal": "...", "artikel_ok": true|false}')
        entry = imgs.get(term_id, {})
        if entry.get("bild"):
            raise SystemExit(f"{EXCLUDE_PATH.name}: {term_id} är utesluten men har ändå en bild")
        if not rule["artikel_ok"] and entry.get("artikel"):
            raise SystemExit(
                f"{EXCLUDE_PATH.name}: {term_id} har artikel_ok=false men "
                f"artikellänken finns kvar: {entry['artikel']}")
    ids = {t["id"] for t in terms}
    stray = sorted(set(imgs) - ids)
    if stray:
        raise SystemExit(f"{IMGS_PATH.name}: {len(stray)} poster saknar term, t.ex. {stray[:3]}")
    for term_id, entry in imgs.items():
        if entry.get("bild") and entry.get("licens", "Okänd") == "Okänd":
            raise SystemExit(f"{IMGS_PATH.name}: {term_id} har bild utan känd licens")
        # Bilden är en subresurs på en https-sida och måste vara https.
        # Länkarna får vara http, men ingenting annat — en javascript:-adress i
        # ett redigerbart metadatafält ska inte kunna bli en klickbar länk.
        if entry.get("bild") and not str(entry["bild"]).startswith("https://"):
            raise SystemExit(f"{IMGS_PATH.name}: {term_id}.bild är inte https: {entry['bild']!r}")
        for key in ("licensurl", "filsida", "artikel"):
            url = entry.get(key)
            if url and not str(url).startswith(("https://", "http://")):
                raise SystemExit(f"{IMGS_PATH.name}: {term_id}.{key} är varken http eller https: {url!r}")

    values = [dump(terms), dump(cats), dump(imgs),
              dump(term_langs), dump(def_langs), dump(ui_langs)]
    for (marker, opener), value in zip(BLOCKS, values):
        html, same = replace_block(html, marker, opener, value)
        in_sync = in_sync and same

    if in_sync:
        print(f"index.html är redan i synk ({len(terms)} termer, {len(cats)} kategorier, "
              f"{len(term_langs)} termspråk, {sum(1 for e in imgs.values() if e.get('bild'))} bilder).")
        return 0

    if args.check:
        print("index.html är inte i synk med data/ — kör python tools/sync_html_data.py",
              file=sys.stderr)
        return 1

    HTML_PATH.write_text(html, encoding="utf-8")
    # samma format som filerna redan har, så diffen bara visar innehåll
    JSON_PATH.write_text(json.dumps(terms, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"index.html uppdaterad ({len(terms)} termer, {len(cats)} kategorier, "
          f"{len(term_langs)} termspråk, {sum(1 for e in imgs.values() if e.get('bild'))} bilder).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
