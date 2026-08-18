#!/usr/bin/env python3
"""Skriv om DATA-blocket i index.html från data/anatomi-termer.json.

Webbappen är avsiktligt en enda fil utan beroenden och har därför termdatan
inbakad. JSON-filen är källan; det här skriptet håller kopian i synk så att
tools/check_data.py alltid går igenom. Numreringen (fältet n) sätts om till
arrayens ordning, så en ny term kan läggas in var som helst i JSON-filen.

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
HTML_PATH = ROOT / "index.html"

MARKER = "const DATA = ["


def dump(terms):
    """Samma kompakta serialisering som index.html redan använder."""
    return json.dumps(terms, ensure_ascii=False, separators=(",", ":"))


def renumber(terms):
    for i, term in enumerate(terms, start=1):
        term["n"] = i
    return terms


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="rapportera drift utan att skriva om något")
    args = parser.parse_args(argv)

    terms = renumber(json.loads(JSON_PATH.read_text(encoding="utf-8")))
    html = HTML_PATH.read_text(encoding="utf-8")

    start = html.find(MARKER)
    if start == -1:
        raise SystemExit(f"index.html: hittade ingen '{MARKER}' -rad")
    open_bracket = html.index("[", start)
    end = html.index("];", open_bracket)

    new_block = dump(terms)
    if html[open_bracket:end + 1] == new_block:
        print(f"index.html är redan i synk ({len(terms)} termer).")
        return 0

    if args.check:
        print("index.html är inte i synk med anatomi-termer.json — "
              "kör python tools/sync_html_data.py", file=sys.stderr)
        return 1

    HTML_PATH.write_text(html[:open_bracket] + new_block + html[end + 1:], encoding="utf-8")
    # samma format som filen redan har, så diffen bara visar innehåll
    JSON_PATH.write_text(json.dumps(terms, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"index.html uppdaterad från {JSON_PATH.name} ({len(terms)} termer).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
