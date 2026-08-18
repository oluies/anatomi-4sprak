#!/usr/bin/env python3
"""Kontrollera termdatans invarianter och att index.html är i synk med JSON-filen.

Webbappen har termdatan inbakad som ``const DATA = [...]`` i index.html medan
build_deck.py läser data/anatomi-termer.json. Det här skriptet ser till att de
två aldrig glider isär, och att fälten som resten av koden förutsätter finns.

Användning:
    python tools/check_data.py
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "anatomi-termer.json"
HTML_PATH = ROOT / "index.html"

REQUIRED = ["id", "cat", "sv", "la", "uk", "ru", "def_sv", "def_uk", "def_ru", "n"]


def inline_data(html_text):
    """Plocka ut DATA-arrayen ur index.html."""
    start = html_text.find("const DATA = [")
    if start == -1:
        raise SystemExit("index.html: hittade ingen 'const DATA = [' -rad")
    open_bracket = html_text.index("[", start)
    end = html_text.index("];", open_bracket)
    raw = html_text[open_bracket:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        # Blocket är JavaScript, så det kan vara giltig JS men ogiltig JSON
        # (avslutande komma, enkla citattecken, kommentarer).
        raise SystemExit(f"index.html: DATA-blocket är inte giltig JSON: {exc}")


def describe_drift(inline, terms):
    """Beskriv exakt var index.html och JSON-filen skiljer sig åt."""
    if inline == terms:
        return []
    if len(inline) != len(terms):
        return [
            f"index.html DATA ({len(inline)} termer) skiljer sig från "
            f"{JSON_PATH.name} ({len(terms)} termer) — uppdatera båda"
        ]
    problems = []
    for i, (a, b) in enumerate(zip(inline, terms)):
        if a == b:
            continue
        tid = b.get("id", a.get("id", "?"))
        diff = sorted(set(a) | set(b))
        fields = [f for f in diff if a.get(f) != b.get(f)]
        detail = ", ".join(
            f"{f}: index.html={a.get(f)!r} vs json={b.get(f)!r}" for f in fields
        )
        problems.append(f"post {i} (id={tid!r}) skiljer sig mellan index.html och JSON — {detail}")
        if len(problems) == 5:
            problems.append("... fler skillnader finns, visar de första fem")
            break
    return problems


def main():
    errors = []
    terms = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    if not terms:
        errors.append("JSON-filen är tom")

    seen_ids, seen_n = {}, {}
    for i, term in enumerate(terms):
        where = f"post {i} (id={term.get('id')!r})"
        for field in REQUIRED:
            if field not in term:
                errors.append(f"{where}: saknar fältet {field}")
            elif isinstance(term[field], str) and not term[field].strip():
                errors.append(f"{where}: fältet {field} är tomt")
        tid, n = term.get("id"), term.get("n")
        if tid in seen_ids:
            errors.append(f"{where}: id {tid!r} används redan av post {seen_ids[tid]}")
        seen_ids[tid] = i
        if n in seen_n:
            errors.append(f"{where}: n={n} används redan av post {seen_n[n]}")
        seen_n[n] = i

    inline = inline_data(HTML_PATH.read_text(encoding="utf-8"))
    errors.extend(describe_drift(inline, terms))

    if errors:
        for e in errors:
            print(f"FEL: {e}", file=sys.stderr)
        return 1

    cats = {}
    for term in terms:
        cats[term["cat"]] = cats.get(term["cat"], 0) + 1
    print(f"OK: {len(terms)} termer i {len(cats)} kategorier, index.html i synk.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
