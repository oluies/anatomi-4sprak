"""Bevisar att ett nytt språk går att lägga till genom att bara röra data/.

Testet lägger till polska i en kopia av repot och kontrollerar att både
webbappen och Anki-decket följer med utan en enda kodändring.
"""

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def repo(tmp_path):
    """Kopiera det som behövs för att köra verktygen fristående."""
    for rel in ["index.html", "tools/sync_html_data.py", "tools/build_deck.py",
                "tools/check_data.py", "tools/fetch_images.py", "data/anatomi-termer.json",
                "data/kategorier.json", "data/sprak.json", "data/bilder.json",
                "data/bilder-uteslutna.json"]:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dst)
    return tmp_path


def run(repo, *args):
    return subprocess.run([sys.executable, *args], cwd=repo,
                          capture_output=True, text=True)


def add_polish(repo):
    sprak = json.loads((repo / "data/sprak.json").read_text(encoding="utf-8"))
    sprak["pl"] = {"namn": "Polski", "term": True, "forklaring": True,
                   "granssnitt": "Polski", "ankifalt": "Polska", "ankidef": "DefPl"}
    (repo / "data/sprak.json").write_text(json.dumps(sprak, ensure_ascii=False, indent=1),
                                          encoding="utf-8")

    cats = json.loads((repo / "data/kategorier.json").read_text(encoding="utf-8"))
    for names in cats.values():
        names["pl"] = "kategoria"
    (repo / "data/kategorier.json").write_text(json.dumps(cats, ensure_ascii=False, indent=1),
                                               encoding="utf-8")


def add_polish_terms(repo):
    path = repo / "data/anatomi-termer.json"
    terms = json.loads(path.read_text(encoding="utf-8"))
    for t in terms:
        t["pl"] = "pl-" + t["id"]
        t["def_pl"] = "Definicja: " + t["id"]
    path.write_text(json.dumps(terms, ensure_ascii=False, indent=1), encoding="utf-8")


def test_sync_refuses_when_terms_lack_the_new_field(repo):
    """Halvfärdig översättning ska stoppas, inte tyst ge tomma kort."""
    add_polish(repo)
    r = run(repo, "tools/sync_html_data.py")
    assert r.returncode != 0
    assert "saknar fältet 'pl'" in r.stderr or "saknar fältet 'pl'" in r.stdout


def test_new_language_reaches_the_app(repo):
    add_polish(repo)
    add_polish_terms(repo)
    assert run(repo, "tools/sync_html_data.py").returncode == 0
    html = (repo / "index.html").read_text(encoding="utf-8")

    langs = json.loads(html.split("const LANGS = ")[1].split(";")[0])
    assert langs["pl"] == "Polski", "polska ska bli valbart term-/svarsspråk"
    defs = json.loads(html.split("const DEFLANGS = ")[1].split(";")[0])
    assert defs["pl"] == "Polski", "polska ska bli valbart förklaringsspråk"
    uis = json.loads(html.split("const UILANGS = ")[1].split(";")[0])
    assert uis["pl"] == "Polski", "polska ska bli valbart gränssnittsspråk"

    # samma extraktion som check_data använder — '];' förekommer flera gånger i filen
    sys.path.insert(0, str(ROOT / "tools"))
    import check_data
    data = check_data.inline_data(html)
    assert all("pl" in t and "def_pl" in t for t in data)
    assert run(repo, "tools/check_data.py").returncode == 0


def test_new_language_reaches_the_deck(repo):
    genanki = pytest.importorskip("genanki")  # noqa: F841
    add_polish(repo)
    add_polish_terms(repo)
    assert run(repo, "tools/sync_html_data.py").returncode == 0
    out = repo / "deck.apkg"
    assert run(repo, "tools/build_deck.py", "--out", str(out)).returncode == 0

    import sqlite3
    import tempfile
    import zipfile
    with zipfile.ZipFile(out) as z:
        name = next(n for n in z.namelist() if n.startswith("collection"))
        db = pathlib.Path(tempfile.mkdtemp()) / "c.anki2"
        db.write_bytes(z.read(name))
    con = sqlite3.connect(db)
    model = list(json.loads(con.execute("select models from col").fetchone()[0]).values())[0]
    fields = [f["name"] for f in model["flds"]]
    templates = [t["name"] for t in model["tmpls"]]

    assert "Polska" in fields and "DefPl" in fields
    assert "Polska → övriga" in templates, "nytt språk ska ge en egen korttyp"

    # Anki kopplar notinnehåll till fält, och befintliga kort till korttyper,
    # via ORDNINGSNUMMER — inte namn. MODEL_ID är pinnad, så de ursprungliga
    # måste ligga kvar på exakt sina platser; nya läggs sist. Utan det här
    # hamnar latin i svenskfältet på alla befintliga kort vid nästa import.
    assert fields[:8] == ["Svenska", "Latin", "Ukrainska", "Ryska",
                          "DefSv", "DefUk", "DefRu", "Kategori"], fields
    assert templates[:4] == ["Svenska → övriga", "Latin → övriga",
                             "Ukrainska → övriga", "Ryska → övriga"], templates

    # Läs tillbaka en not och kontrollera att innehållet ligger på rätt plats.
    row = con.execute("select flds from notes limit 1").fetchone()[0].split("\x1f")
    terms = {t["id"]: t for t in json.loads(
        (repo / "data/anatomi-termer.json").read_text(encoding="utf-8"))}
    match = next(t for t in terms.values() if t["sv"] == row[0])
    assert row[1] == match["la"], "latin ska ligga på plats 1"
    assert row[2] == match["uk"] and row[3] == match["ru"]
    assert row[4] == match["def_sv"], "DefSv ska ligga på plats 4"
    assert row[7] == match["cat"], "Kategori ska ligga på plats 7"
    assert row[8] == match["pl"], "nytt språk ska hamna sist"


def test_language_inserted_first_still_keeps_field_ordinals(repo):
    """Även ett språk som skrivs in FÖRST i sprak.json får inte flytta fälten."""
    pytest.importorskip("genanki")
    import sqlite3
    import tempfile
    import zipfile

    path = repo / "data/sprak.json"
    sprak = json.loads(path.read_text(encoding="utf-8"))
    reordered = {"pl": {"namn": "Polski", "term": True, "forklaring": True,
                        "granssnitt": "Polski", "ankifalt": "Polska", "ankidef": "DefPl"}}
    reordered.update(sprak)
    path.write_text(json.dumps(reordered, ensure_ascii=False, indent=1), encoding="utf-8")
    cats = json.loads((repo / "data/kategorier.json").read_text(encoding="utf-8"))
    for names in cats.values():
        names["pl"] = "kategoria"
    (repo / "data/kategorier.json").write_text(
        json.dumps(cats, ensure_ascii=False, indent=1), encoding="utf-8")
    add_polish_terms(repo)

    out = repo / "deck.apkg"
    assert run(repo, "tools/build_deck.py", "--out", str(out)).returncode == 0
    with zipfile.ZipFile(out) as z:
        name = next(n for n in z.namelist() if n.startswith("collection"))
        db = pathlib.Path(tempfile.mkdtemp()) / "c.anki2"
        db.write_bytes(z.read(name))
    model = list(json.loads(sqlite3.connect(db).execute(
        "select models from col").fetchone()[0]).values())[0]
    assert [f["name"] for f in model["flds"]][:8] == [
        "Svenska", "Latin", "Ukrainska", "Ryska", "DefSv", "DefUk", "DefRu", "Kategori"]
    assert [t["name"] for t in model["tmpls"]][:4] == [
        "Svenska → övriga", "Latin → övriga", "Ukrainska → övriga", "Ryska → övriga"]


def test_existing_guids_survive_a_new_language(repo):
    """Ett nytt språk får inte ge nya guid:n — då dubbleras korten vid import."""
    pytest.importorskip("genanki")
    import sqlite3
    import tempfile
    import zipfile

    def guids(path):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.startswith("collection"))
            db = pathlib.Path(tempfile.mkdtemp()) / "c.anki2"
            db.write_bytes(z.read(name))
        return {r[0] for r in sqlite3.connect(db).execute("select guid from notes")}

    before = repo / "before.apkg"
    assert run(repo, "tools/build_deck.py", "--out", str(before)).returncode == 0
    add_polish(repo)
    add_polish_terms(repo)
    assert run(repo, "tools/sync_html_data.py").returncode == 0
    after = repo / "after.apkg"
    assert run(repo, "tools/build_deck.py", "--out", str(after)).returncode == 0

    assert guids(before) == guids(after)
