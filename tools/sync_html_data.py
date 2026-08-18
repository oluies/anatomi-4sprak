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
    begin = html.index(opener, start)
    end = html.index({"[": "];", "{": "};"}[opener], begin)
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
        raise SystemExit(f"{CATS_PATH.name}: {unused} används inte av någon term")

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
    imgs = json.loads(IMGS_PATH.read_text(encoding="utf-8")) if IMGS_PATH.exists() else {}
    ids = {t["id"] for t in terms}
    stray = sorted(set(imgs) - ids)
    if stray:
        raise SystemExit(f"{IMGS_PATH.name}: {len(stray)} poster saknar term, t.ex. {stray[:3]}")
    for term_id, entry in imgs.items():
        if entry.get("bild") and not entry.get("licens"):
            raise SystemExit(f"{IMGS_PATH.name}: {term_id} har bild utan licensuppgift")

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
