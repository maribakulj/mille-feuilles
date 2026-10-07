"""Explicit selection and isolated CLI routing for the structural diagnostic."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from mille_feuilles import cli


@pytest.mark.parametrize("selection,pages,all_pages", [
    (["--page", "mf_0003", "--page", "mf_0000"], ["mf_0003", "mf_0000"], False),
    (["--all-pages"], None, True),
])
def test_structure_command_routes_without_render_or_full_validation(
    monkeypatch, capsys, selection, pages, all_pages,
):
    calls = []

    def build_report(source, output, **kwargs):
        calls.append((source, output, kwargs))
        return {"status": "pass", "scope": "calculation only; not a realism verdict"}

    def forbidden(*args, **kwargs):
        pytest.fail("The structural report must not render or validate the whole dataset")

    monkeypatch.setitem(sys.modules, "mille_feuilles.structure_report", SimpleNamespace(build_report=build_report))
    monkeypatch.setattr(cli, "build_dataset", forbidden)
    monkeypatch.setattr(cli, "validate_dataset", forbidden)
    assert cli.main(["report-structure", "--from", "source", "--output", "report",
                     "--reference", "read", *selection]) == 0
    assert calls == [(Path("source"), Path("report"),
                      {"page_ids": pages, "all_pages": all_pages, "reference": "read"})]
    assert json.loads(capsys.readouterr().out)["status"] == "pass"


@pytest.mark.parametrize("selection", [[], ["--all-pages", "--page", "mf_0000"]])
def test_structure_requires_one_explicit_selection(capsys, selection):
    with pytest.raises(SystemExit) as exc:
        cli.main(["report-structure", "--from", "source", "--output", "report", *selection])
    assert exc.value.code == 2
    assert capsys.readouterr().out == ""


def test_structure_refusal_has_no_success_json(monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise ValueError("canonical hash mismatch")

    monkeypatch.setitem(sys.modules, "mille_feuilles.structure_report", SimpleNamespace(build_report=refuse))
    assert cli.main(["report-structure", "--from", "source", "--output", "report", "--all-pages"]) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "canonical hash mismatch" in output.err
