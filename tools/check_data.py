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
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "anatomi-termer.json"
HTML_PATH = ROOT / "index.html"

LANGS_PATH = ROOT / "data" / "sprak.json"


def required_fields():
    """Fältlistan härleds ur data/sprak.json så att ett nytt språk kontrolleras
    utan att den här filen behöver ändras."""
    fields = ["id", "cat"]
    langs = json.loads(LANGS_PATH.read_text(encoding="utf-8"))
    fields += [k for k, v in langs.items() if v.get("term")]
    fields += ["def_" + k for k, v in langs.items() if v.get("forklaring")]
    return fields + ["n"]


REQUIRED = required_fields()

# Så många skiljande poster rapporteras innan listan kortas av.
MAX_REPORTED = 5


def require_list_of_dicts(items, source):
    """Resten av skriptet indexerar posterna som dictar — kontrollera det först,
    annars faller kontrollen på en rå AttributeError i stället för ett läsbart fel."""
    if not isinstance(items, list):
        raise SystemExit(f"{source}: förväntade en lista av termer, fick {type(items).__name__}")
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"{source}: post {i} är {type(item).__name__}, förväntade ett objekt")
    return items


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


def _fold(text):
    """Gemener utan diakriter och skiljetecken, för jämförelse av termformer."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z ]", "", text).strip()


def latin_in_swedish(terms):
    """Den svenska termen ska inte upprepa sitt eget latinska namn i parentes.

    Latinet har ett eget fält och visas som eget svar; en dubblett i sv-fältet
    avslöjar svaret när latin är svarsspråk. Svenska förklaringar i parentes,
    som "anterior (främre)", är avsiktliga och rapporteras inte.

    Alla parenteser granskas, inte bara den första, och parentesen jämförs både
    mot hela det latinska namnet och mot dess enskilda ord — "tarmben (ilium)"
    med la "os ilium" röjer svaret lika mycket som en exakt träff.
    """
    problems = []
    for term in terms:
        sv = str(term.get("sv", ""))
        la = str(term.get("la", ""))
        folded_la = _fold(la)
        if not folded_la:
            continue
        # Ord som är för korta för att vara avslöjande på egen hand.
        words = {w for w in folded_la.split() if len(w) > 3}
        for match in re.finditer(r"\(([^)]*)\)", sv):
            inner = _fold(match.group(1))
            if not inner:
                continue
            if inner == folded_la or inner in words:
                problems.append(
                    f"post id={term.get('id')!r}: sv {sv!r} upprepar latinet "
                    f"{la!r} — ta bort parentesen"
                )
                break
    return problems


def describe_drift(inline, terms):
    """Beskriv exakt var index.html och JSON-filen skiljer sig åt."""
    if inline == terms:
        return []
    if len(inline) != len(terms):
        return [
            f"index.html DATA ({len(inline)} termer) skiljer sig från "
            f"{JSON_PATH.name} ({len(terms)} termer) — uppdatera båda"
        ]
    differing = [i for i, (a, b) in enumerate(zip(inline, terms)) if a != b]
    problems = []
    for i in differing[:MAX_REPORTED]:
        a, b = inline[i], terms[i]
        tid = b.get("id", a.get("id", "?"))
        fields = [f for f in sorted(set(a) | set(b)) if a.get(f) != b.get(f)]
        detail = ", ".join(
            f"{f}: index.html={a.get(f)!r} vs json={b.get(f)!r}" for f in fields
        )
        problems.append(f"post {i} (id={tid!r}) skiljer sig mellan index.html och JSON — {detail}")
    if len(differing) > MAX_REPORTED:
        problems.append(
            f"... {len(differing) - MAX_REPORTED} skillnader till, "
            f"visar de första {MAX_REPORTED}"
        )
    return problems


def main():
    errors = []
    terms = require_list_of_dicts(
        json.loads(JSON_PATH.read_text(encoding="utf-8")), JSON_PATH.name
    )

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

    errors.extend(latin_in_swedish(terms))

    inline = require_list_of_dicts(
        inline_data(HTML_PATH.read_text(encoding="utf-8")), "index.html DATA"
    )
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
