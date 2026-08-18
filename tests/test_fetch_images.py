"""Tester för de nätverksfria delarna av tools/fetch_images.py.

Buggen som kostade 169 av 263 licenser — pageimages ger filnamnet med
understreck medan imageinfo returnerar titeln med mellanslag — fixades utan
test. Den här filen täcker just den normaliseringen och grannfunktionerna.
"""

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import fetch_images as fi  # noqa: E402


def test_strip_paren_and_affix():
    assert fi.strip_paren("lymfknuta (lymfkörtel)") == "lymfknuta"
    assert fi.strip_paren("armbågsben") == "armbågsben"
    assert fi.is_affix({"sv": "-emi (tillstånd i blodet)"})
    assert fi.is_affix({"sv": "hyper- (över)"})
    assert not fi.is_affix({"sv": "armbågsben"})


def test_clean_url_drops_tracking_params():
    assert fi.clean_url("https://x/y.png?utm_source=api") == "https://x/y.png"
    assert fi.clean_url(None) is None


def test_https_url_upgrades_creative_commons_links():
    assert fi.https_url("http://creativecommons.org/licenses/by-sa/3.0/") \
        == "https://creativecommons.org/licenses/by-sa/3.0/"
    assert fi.https_url("https://example.org/") == "https://example.org/"
    assert fi.https_url("") == ""


def test_strip_html():
    assert fi.strip_html("<a href='x'>Patrick J. Lynch</a>") == "Patrick J. Lynch"
    assert fi.strip_html(None) == ""


def test_license_lookup_matches_underscored_filenames(monkeypatch):
    """pageimages ger 'Human_Hepar.jpg', API:et svarar 'Fil:Human Hepar.jpg'."""
    payload = {"query": {"pages": [{
        "title": "Fil:Human Hepar.jpg",
        "imageinfo": [{
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Human_Hepar.jpg",
            "extmetadata": {
                "Artist": {"value": "<a>Patrick J. Lynch</a>"},
                "LicenseShortName": {"value": "CC BY 2.5"},
                "LicenseUrl": {"value": "http://creativecommons.org/licenses/by/2.5/"},
            }}]}]}}
    monkeypatch.setattr(fi, "api", lambda params: payload)
    monkeypatch.setattr(fi.time, "sleep", lambda *_: None)

    out = fi.lookup_licenses(["Human_Hepar.jpg"])
    assert "Human_Hepar.jpg" in out, "understreck/mellanslag måste normaliseras"
    entry = out["Human_Hepar.jpg"]
    assert entry["upphov"] == "Patrick J. Lynch"
    assert entry["licens"] == "CC BY 2.5"
    assert entry["licensurl"].startswith("https://")


def test_license_lookup_handles_empty_extmetadata(monkeypatch):
    """extmetadata kommer tillbaka som tom lista när filtret inte matchar."""
    payload = {"query": {"pages": [
        {"title": "Fil:X.jpg", "imageinfo": [{"extmetadata": []}]}]}}
    monkeypatch.setattr(fi, "api", lambda params: payload)
    monkeypatch.setattr(fi.time, "sleep", lambda *_: None)
    entry = fi.lookup_licenses(["X.jpg"])["X.jpg"]
    assert entry["upphov"] == "Okänd" and entry["licens"] == "Okänd"


def test_lookup_pages_follows_redirects_and_normalisation(monkeypatch):
    payload = {"query": {
        "normalized": [{"from": "lever", "to": "Lever"}],
        "redirects": [{"from": "Lever", "to": "Levern"}],
        "pages": [{"title": "Levern", "pageimage": "L.jpg",
                   "thumbnail": {"source": "https://u/L.jpg?utm_source=api"}}]}}
    monkeypatch.setattr(fi, "api", lambda params: payload)
    monkeypatch.setattr(fi.time, "sleep", lambda *_: None)
    pages = fi.lookup_pages(["lever"])
    assert "lever" in pages and pages["lever"]["pageimage"] == "L.jpg"


def test_drop_image_clears_all_credit_keys():
    entry = {"artikel": "a", "bild": "b", "licens": "c",
             "upphov": "d", "licensurl": "e", "filsida": "f"}
    assert fi.drop_image(entry) is True
    assert entry == {"artikel": "a"}, "kreditfält får inte bli kvar utan bild"


def test_homonym_exclusion_also_drops_the_article():
    """Vid homonym är uppslaget fel — artikellänken skickar eleven vilse."""
    entry = {"artikel": "https://sv.wikipedia.org/wiki/Atlas", "bild": "b", "licens": "c"}
    fi.drop_image(entry, drop_article=fi.is_homonym("homonym: titanen"))
    assert entry == {}
    keep = {"artikel": "https://sv.wikipedia.org/wiki/Tonsill", "bild": "b", "licens": "c"}
    fi.drop_image(keep, drop_article=fi.is_homonym("klottrat upphovsfält"))
    assert keep == {"artikel": "https://sv.wikipedia.org/wiki/Tonsill"}


def test_load_excluded_ignores_comment_keys(monkeypatch, tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"_kommentar": "text", "atlas": "homonym"}), encoding="utf-8")
    monkeypatch.setattr(fi, "EXCLUDE_PATH", path)
    assert fi.load_excluded() == {"atlas": "homonym"}


def test_committed_data_has_no_orphan_credits_or_bad_urls():
    """Vaktposter mot den faktiska datan i repot."""
    data = json.loads((ROOT / "data" / "bilder.json").read_text(encoding="utf-8"))
    for term_id, entry in data.items():
        if not entry.get("bild"):
            for key in ("licens", "upphov", "licensurl", "filsida"):
                assert key not in entry, f"{term_id}: {key} kvar utan bild"
        else:
            assert entry.get("licens", "Okänd") != "Okänd", f"{term_id}: bild utan licens"
            assert entry["bild"].startswith("https://"), f"{term_id}: bild inte https"
    excluded = json.loads((ROOT / "data" / "bilder-uteslutna.json").read_text(encoding="utf-8"))
    for term_id, reason in excluded.items():
        if term_id.startswith("_"):
            continue
        if fi.is_homonym(reason):
            assert "artikel" not in data.get(term_id, {}), \
                f"{term_id}: homonym men artikellänken finns kvar"
