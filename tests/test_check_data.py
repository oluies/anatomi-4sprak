"""Tester för tools/check_data.py — den enda vakten mot att index.html och
anatomi-termer.json glider isär, och mot dubbletter av id/n som annars tyst
slår ihop kort vid Anki-import."""

import json
import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_data  # noqa: E402


def term(i, **overrides):
    t = {
        "id": f"term{i}",
        "cat": "Skelettet",
        "sv": f"svenska{i}",
        "la": f"latin{i}",
        "uk": f"укр{i}",
        "ru": f"рус{i}",
        "def_sv": f"förklaring {i}",
        "def_uk": f"пояснення {i}",
        "def_ru": f"пояснение {i}",
        "n": i,
    }
    t.update(overrides)
    return t


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Skriv ett minirepo och peka check_data på det."""

    def write(terms, inline=None):
        json_path = tmp_path / "anatomi-termer.json"
        html_path = tmp_path / "index.html"
        json_path.write_text(json.dumps(terms, ensure_ascii=False), encoding="utf-8")
        body = json.dumps(terms if inline is None else inline, ensure_ascii=False)
        html_path.write_text(
            f"<html><script>\nconst DATA = {body};\n</script></html>", encoding="utf-8"
        )
        monkeypatch.setattr(check_data, "JSON_PATH", json_path)
        monkeypatch.setattr(check_data, "HTML_PATH", html_path)
        return html_path

    return write


def test_happy_path(repo):
    repo([term(1), term(2)])
    assert check_data.main() == 0


def test_duplicate_id(repo, capsys):
    repo([term(1), term(2, id="term1")])
    assert check_data.main() == 1
    assert "id 'term1' används redan" in capsys.readouterr().err


def test_duplicate_n(repo, capsys):
    repo([term(1), term(2, n=1)])
    assert check_data.main() == 1
    assert "n=1 används redan" in capsys.readouterr().err


def test_empty_field(repo, capsys):
    repo([term(1, def_uk="   ")])
    assert check_data.main() == 1
    assert "def_uk är tomt" in capsys.readouterr().err


def test_missing_field(repo, capsys):
    t = term(1)
    del t["la"]
    repo([t])
    assert check_data.main() == 1
    assert "saknar fältet la" in capsys.readouterr().err


def test_inline_drift_same_length_names_the_field(repo, capsys):
    """Den vanligaste driften: en term ändrad på ett ställe men inte det andra."""
    repo([term(1), term(2)], inline=[term(1), term(2, uk="ändrad")])
    assert check_data.main() == 1
    err = capsys.readouterr().err
    assert "id='term2'" in err
    assert "uk:" in err


def test_inline_drift_different_length(repo, capsys):
    repo([term(1), term(2)], inline=[term(1)])
    assert check_data.main() == 1
    assert "1 termer) skiljer sig" in capsys.readouterr().err


def test_invalid_inline_json(tmp_path, monkeypatch):
    json_path = tmp_path / "anatomi-termer.json"
    html_path = tmp_path / "index.html"
    json_path.write_text(json.dumps([term(1)], ensure_ascii=False), encoding="utf-8")
    # Giltig JS, ogiltig JSON (avslutande komma).
    html_path.write_text("<script>const DATA = [{\"id\":\"a\",},];</script>", encoding="utf-8")
    monkeypatch.setattr(check_data, "JSON_PATH", json_path)
    monkeypatch.setattr(check_data, "HTML_PATH", html_path)
    with pytest.raises(SystemExit) as exc:
        check_data.main()
    assert "inte giltig JSON" in str(exc.value)


def test_missing_data_block(tmp_path, monkeypatch):
    json_path = tmp_path / "anatomi-termer.json"
    html_path = tmp_path / "index.html"
    json_path.write_text(json.dumps([term(1)], ensure_ascii=False), encoding="utf-8")
    html_path.write_text("<html>ingen data här</html>", encoding="utf-8")
    monkeypatch.setattr(check_data, "JSON_PATH", json_path)
    monkeypatch.setattr(check_data, "HTML_PATH", html_path)
    with pytest.raises(SystemExit) as exc:
        check_data.main()
    assert "const DATA" in str(exc.value)


def test_real_repo_data_is_valid():
    """Den riktiga datan i repot ska alltid passera."""
    assert check_data.main() == 0


def test_truncation_note_only_when_truncated(repo, capsys):
    """Exakt fem skillnader ska rapporteras utan '... fler skillnader'-noten."""
    terms = [term(i) for i in range(1, 8)]
    inline = [dict(t) for t in terms]
    for t in inline[:5]:
        t["uk"] = "ändrad"
    repo(terms, inline=inline)
    assert check_data.main() == 1
    err = capsys.readouterr().err
    assert err.count("skiljer sig mellan index.html och JSON") == 5
    assert "skillnader till" not in err


def test_truncation_note_when_more_than_five(repo, capsys):
    terms = [term(i) for i in range(1, 10)]
    inline = [dict(t) for t in terms]
    for t in inline:
        t["uk"] = "ändrad"
    repo(terms, inline=inline)
    assert check_data.main() == 1
    err = capsys.readouterr().err
    assert "4 skillnader till, visar de första 5" in err


def test_non_dict_entries_give_readable_error(tmp_path, monkeypatch):
    json_path = tmp_path / "anatomi-termer.json"
    html_path = tmp_path / "index.html"
    json_path.write_text(json.dumps([term(1), "inte ett objekt"], ensure_ascii=False), encoding="utf-8")
    html_path.write_text("<script>const DATA = [];</script>", encoding="utf-8")
    monkeypatch.setattr(check_data, "JSON_PATH", json_path)
    monkeypatch.setattr(check_data, "HTML_PATH", html_path)
    with pytest.raises(SystemExit) as exc:
        check_data.main()
    assert "post 1 är str" in str(exc.value)


def test_non_dict_entry_in_index_html(tmp_path, monkeypatch):
    """DATA-blocket är handredigerad JavaScript — samma typkontroll måste gälla där."""
    json_path = tmp_path / "anatomi-termer.json"
    html_path = tmp_path / "index.html"
    json_path.write_text(json.dumps([term(1)], ensure_ascii=False), encoding="utf-8")
    html_path.write_text('<script>const DATA = ["inte ett objekt"];</script>', encoding="utf-8")
    monkeypatch.setattr(check_data, "JSON_PATH", json_path)
    monkeypatch.setattr(check_data, "HTML_PATH", html_path)
    with pytest.raises(SystemExit) as exc:
        check_data.main()
    assert "index.html DATA" in str(exc.value)
    assert "post 0 är str" in str(exc.value)
