"""The versioned multi-document import example is reproducible and imports cleanly."""

import json
import subprocess
import sys

from mille_feuilles.catalog import import_texts, text_units
from mille_feuilles.io import ROOT

SOURCE = ROOT / "assets/import-demo/presse-multi"
TOWNS = {"velmont", "castelbrune", "lisserand", "hautbrume", "corvelle"}


def rows():
    return [json.loads(line) for line in (SOURCE / "import.jsonl").read_text(encoding="utf-8").splitlines()]


def test_sources_are_reproduced_exactly_by_their_builder(tmp_path):
    copy = tmp_path / "presse-multi"
    copy.mkdir()
    (copy / "build_sources.py").write_bytes((SOURCE / "build_sources.py").read_bytes())
    subprocess.run([sys.executable, str(copy / "build_sources.py")], check=True)
    built = {p.relative_to(copy).as_posix(): p.read_bytes() for p in copy.rglob("*") if p.is_file()}
    versioned = {p.relative_to(SOURCE).as_posix(): p.read_bytes() for p in SOURCE.rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts}
    assert built == versioned


def test_each_town_has_two_eligible_bodies_titles_and_notices():
    by_group = {}
    for row in rows():
        by_group.setdefault(row["source_group_id"], []).append(row)
        assert row["historical_corpus"] is False and row["rights"]["license"] == "CC0-1.0"
    assert {group.removeprefix("mf-presse-multi-") for group in by_group} == TOWNS
    for group_rows in by_group.values():
        roles = [row["role"] for row in group_rows]
        assert sorted(roles) == ["advertisement", "body", "body", "title"]
        for row in group_rows:
            if row["role"] == "body":
                text = (SOURCE / row["path"]).read_text(encoding="utf-8")
                assert len(text_units(text, "body")) == 5


def test_example_imports_without_rejection(tmp_path):
    report = import_texts(SOURCE / "import.jsonl", tmp_path / "bundle", {})
    assert report["status"] == "pass" and report["rejected"] == []
    assert len(report["accepted"]) == 20
    assert report["external_protection"] == "NOT EVALUATED"
