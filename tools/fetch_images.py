#!/usr/bin/env python3
"""Slå upp en bild per term på svenskspråkiga Wikipedia och spara metadatan.

Bilderna hotlänkas från upload.wikimedia.org; det här skriptet lagrar bara
URL:en, artikellänken och licensuppgifterna i data/bilder.json. Licensraden
måste visas tillsammans med bilden — flera bilder är CC BY-SA och kräver
namngivning av upphovspersonen.

Skriptet är avsiktligt inte en del av bygget: det anropar Wikipedias API och
körs för hand när man vill uppdatera bildurvalet.

Användning:
    python tools/fetch_images.py                 # uppdatera data/bilder.json
    python tools/fetch_images.py --only Skelettet  # bara en kategori
    python tools/fetch_images.py --dry-run       # visa vad som skulle sparas
"""

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "anatomi-termer.json"
OUT_PATH = ROOT / "data" / "bilder.json"
EXCLUDE_PATH = ROOT / "data" / "bilder-uteslutna.json"

API = "https://sv.wikipedia.org/w/api.php"
# Wikimedia kräver en User-Agent som går att kontakta.
UA = ("anatomi-4sprak/1.0 (https://github.com/oluies/anatomi-4sprak; "
      "orjan.lundberg@gmail.com)")
THUMB_WIDTH = 400
BATCH = 40
PAUSE = 0.3

# Prefix och suffix ("hyper-", "-emi") och rena riktningsord har inga
# meningsfulla bilder — hoppa över dem i stället för att hämta brus.
SKIP_CATEGORIES = set()


def strip_paren(text):
    return re.sub(r"\s*\([^)]*\)", "", text).strip()


def is_affix(term):
    sv = term["sv"]
    return sv.startswith("-") or sv.endswith("-") or "/" in sv


def api(params):
    # formatversion 2 ger pages som lista och slipper pageid-nycklade objekt
    params = dict(params, format="json", formatversion="2")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as fh:
        return json.load(fh)


def clean_url(url):
    """Ta bort API:ets utm-parametrar ur tumnagel-URL:en."""
    return url.split("?")[0] if url else None


# Upphovsfältet på Commons är fritext och kan vara en hel licensuppsats — eller
# klotter. Kapa det till en kreditrad som får plats; filsidan länkas alltid och
# bär den fullständiga uppgiften.
MAX_CREDIT = 80


def strip_html(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def shorten(text, limit=MAX_CREDIT):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return (cut or text[:limit]) + "…"


def lookup_pages(titles):
    """Slå upp artiklarna och deras huvudbild. Returnerar {sökt titel: sida}."""
    result = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        data = api({"action": "query", "prop": "pageimages",
                    "piprop": "thumbnail|name", "pithumbsize": THUMB_WIDTH,
                    "pilicense": "free", "redirects": 1, "titles": "|".join(chunk)})
        query = data.get("query", {})
        alias = {}
        for key in ("normalized", "redirects"):
            for entry in query.get(key, []):
                alias[entry["from"]] = entry["to"]
        pages = {p["title"]: p for p in query.get("pages", [])}

        def resolve(title):
            seen = set()
            while title in alias and title not in seen:
                seen.add(title)
                title = alias[title]
            return title

        for title in chunk:
            page = pages.get(resolve(title))
            if page and "missing" not in page:
                result[title] = page
        time.sleep(PAUSE)
    return result


# Wikidata-egenskaper som bara anatomiska strukturer har. Saknas de allihop är
# artikeln ofta en homonym — "atlas" blev titanen, "lins" den optiska linsen.
ANATOMY_PROPS = ["P1402", "P7827", "P1554", "P486"]


def suspicious_articles(titles):
    """Returnera de artiklar som saknar anatomisk identifierare i Wikidata."""
    qids = {}
    for i in range(0, len(titles), BATCH):
        data = api({"action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
                    "titles": "|".join(titles[i:i + BATCH])})
        for page in data.get("query", {}).get("pages", []):
            qid = (page.get("pageprops") or {}).get("wikibase_item")
            if qid:
                qids[page["title"]] = qid
        time.sleep(PAUSE)

    anatomical = set()
    ids = sorted(set(qids.values()))
    for i in range(0, len(ids), 50):
        url = ("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": "|".join(ids[i:i + 50]),
             "props": "claims", "format": "json"}))
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=40) as fh:
            entities = json.load(fh).get("entities", {})
        for qid, entity in entities.items():
            if any(p in entity.get("claims", {}) for p in ANATOMY_PROPS):
                anatomical.add(qid)
        time.sleep(PAUSE)

    return {t for t in titles if qids.get(t) not in anatomical}


def lookup_licenses(filenames):
    """Hämta upphovsperson och licens för varje filnamn."""
    result = {}
    names = sorted({n.replace(" ", "_") for n in filenames})
    for i in range(0, len(names), BATCH):
        chunk = names[i:i + BATCH]
        data = api({"action": "query", "prop": "imageinfo",
                    "iiprop": "extmetadata|url",
                    "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl|Credit",
                    "titles": "|".join("File:" + n for n in chunk)})
        for page in data.get("query", {}).get("pages", []):
            info = (page.get("imageinfo") or [{}])[0]
            # extmetadata kommer tillbaka som tom lista när filtret inte matchar
            meta = info.get("extmetadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            # pageimage använder understreck ("Human_Hepar.jpg") medan API:et
            # returnerar titeln med mellanslag ("Fil:Human Hepar.jpg") — utan
            # normaliseringen matchar nycklarna aldrig och licensen blir okänd.
            key = page["title"].split(":", 1)[-1].replace(" ", "_")
            field = lambda name: (meta.get(name) or {}).get("value") if isinstance(meta.get(name), dict) else None
            result[key] = {
                "upphov": shorten(strip_html(field("Artist"))) or "Okänd",
                "licens": strip_html(field("LicenseShortName")) or "Okänd",
                "licensurl": field("LicenseUrl") or "",
                "filsida": info.get("descriptionurl", ""),
            }
        time.sleep(PAUSE)
    return result


def load_excluded():
    """Term-id vars automatiskt valda bild har underkänts vid granskning."""
    if not EXCLUDE_PATH.exists():
        return {}
    raw = json.loads(EXCLUDE_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def build(terms, dry_run=False):
    excluded = load_excluded()
    wanted = [t for t in terms if not is_affix(t) and t["cat"] not in SKIP_CATEGORIES]
    titles = {t["id"]: strip_paren(t["sv"]) for t in wanted}
    pages = lookup_pages(sorted(set(titles.values())))

    entries, no_article, no_image = {}, [], []
    for term in wanted:
        page = pages.get(titles[term["id"]])
        if not page:
            no_article.append(term["sv"])
            continue
        article = "https://sv.wikipedia.org/wiki/" + urllib.parse.quote(page["title"].replace(" ", "_"))
        thumb = clean_url((page.get("thumbnail") or {}).get("source"))
        if not thumb:
            no_image.append(term["sv"])
            entries[term["id"]] = {"artikel": article}
            continue
        entries[term["id"]] = {"artikel": article, "bild": thumb,
                               "fil": page.get("pageimage", "")}

    licenses = lookup_licenses([e["fil"] for e in entries.values() if e.get("fil")])
    unresolved = []
    for entry in entries.values():
        name = (entry.pop("fil", "") or "").replace(" ", "_")
        meta = licenses.get(name)
        if meta:
            entry.update(meta)
        elif entry.get("bild"):
            unresolved.append(name)
    if unresolved:
        # Utan licens och upphovsperson får bilden inte publiceras.
        print(f"VARNING: {len(unresolved)} bilder saknar licensuppgifter "
              f"och utelämnas: {unresolved[:5]}", file=sys.stderr)
        for entry in entries.values():
            if entry.get("bild") and not entry.get("licens"):
                entry.pop("bild", None)

    for term_id, reason in excluded.items():
        if term_id in entries and entries[term_id].pop("bild", None):
            entries[term_id].pop("licens", None)
            entries[term_id].pop("upphov", None)
            entries[term_id].pop("licensurl", None)
            entries[term_id].pop("filsida", None)
            print(f"  utesluten vid granskning: {term_id} ({reason})")

    # Utan känd licens och upphovsperson får bilden inte publiceras.
    for term_id, entry in entries.items():
        if entry.get("bild") and entry.get("licens", "Okänd") == "Okänd":
            print(f"  utan känd licens, utelämnas: {term_id}")
            entry.pop("bild", None)

    # Flagga misstänkta homonymer så att de kan granskas och vid behov föras in
    # i bilder-uteslutna.json. Automatiskt bortval vore fel: flera korrekta
    # artiklar (Bröstkorg, Penis, Förlossning) saknar också identifierarna.
    article_of = {}
    for term in wanted:
        entry = entries.get(term["id"])
        if entry and entry.get("bild"):
            article_of[term["id"]] = urllib.parse.unquote(
                entry["artikel"].rsplit("/", 1)[-1]).replace("_", " ")
    if article_of:
        suspect = suspicious_articles(sorted(set(article_of.values())))
        flagged = [(tid, art) for tid, art in article_of.items() if art in suspect]
        if flagged:
            print(f"\n  {len(flagged)} artiklar saknar anatomisk identifierare i Wikidata "
                  f"— granska att det inte är homonymer:")
            for tid, art in sorted(flagged):
                print(f"    {tid:28} -> {art}")

    with_image = sum(1 for e in entries.values() if e.get("bild"))
    print(f"{len(wanted)} termer slogs upp "
          f"(prefix/suffix undantagna: {len(terms) - len(wanted)})")
    print(f"  artikel:       {len(entries)}")
    print(f"  med bild:      {with_image}")
    print(f"  utan artikel:  {len(no_article)}")
    print(f"  utan bild:     {len(no_image)}")

    if dry_run:
        print("\n--dry-run: inget skrevs")
        return entries

    ordered = {t["id"]: entries[t["id"]] for t in terms if t["id"] in entries}
    OUT_PATH.write_text(json.dumps(ordered, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nskrev {OUT_PATH.relative_to(ROOT)}")
    return entries


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="begränsa till en kategori")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    terms = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    if args.only:
        terms = [t for t in terms if t["cat"] == args.only]
        if not terms:
            raise SystemExit(f"ingen kategori som heter {args.only!r}")
    build(terms, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
