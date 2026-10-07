"""A complete two-page replay plus preflight refusals, using synthetic assets."""

from copy import deepcopy
import importlib.util
from types import SimpleNamespace
import shutil

import pytest

from mille_feuilles import pipeline
from mille_feuilles.io import ROOT, sha256, write_json
from mille_feuilles.render import Config
from mille_feuilles.validation import load_json


@pytest.fixture(scope="module")
def replay_tool():
    spec = importlib.util.spec_from_file_location(
        "reproduce_pilot", ROOT / "tools/reproduce_pilot.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def two_pages(tmp_path_factory):
    root = tmp_path_factory.mktemp("source_lot")
    result = pipeline.build_dataset(
        root,
        Config(width=800, height=1100, columns=4, degradation="mixed", seed=871),
        count=2,
        jobs=1,
    )
    assert result["status"] == "pass", result["errors"]
    return root


def snapshot(root):
    return {str(path.relative_to(root)): sha256(path) for path in root.rglob("*") if path.is_file()}


def test_reproduce_all_images_and_json_bit_for_bit(two_pages, tmp_path, replay_tool):
    before = snapshot(two_pages)
    output = tmp_path / "reproduced"
    report_file = tmp_path / "proof.json"
    progress = []
    report = replay_tool.reproduce(two_pages, output, report_file, progress.append)
    assert report["status"] == "pass", report
    assert report["pages_expected"] == report["pages_reproduced"] == 2
    assert report["files_compared"] == 4
    assert report["mismatches"] == report["errors"] == []
    assert report["environment"]["match"] is True
    assert report["source_manifest_sha256"] == sha256(two_pages / "manifest.json")
    assert report["source_commit"] == load_json(two_pages / "manifest.json")["generator"]["commit"]
    assert len(progress) == 2
    assert load_json(report_file) == report
    for folder in ("images", "pages"):
        generated = sorted((output / folder).glob("*"))
        assert len(generated) == 2
        for path in generated:
            assert path.read_bytes() == (two_pages / folder / path.name).read_bytes()
    assert not (output / "exports").exists()
    assert not (output / "qa").exists()
    assert snapshot(two_pages) == before


def test_nonempty_destination_is_refused_unchanged(two_pages, tmp_path, replay_tool):
    output = tmp_path / "existing"
    output.mkdir()
    witness = output / "owned.txt"
    witness.write_bytes(b"owned bytes\0\xff")
    before = snapshot(output)
    report = replay_tool.reproduce(two_pages, output)
    assert report["status"] == "fail"
    assert report["files_compared"] == report["pages_reproduced"] == 0
    assert "non vide" in report["errors"][0]
    assert snapshot(output) == before


def test_environment_mismatch_is_refused_before_output_creation(two_pages, tmp_path, replay_tool):
    altered = tmp_path / "altered_source"
    shutil.copytree(two_pages, altered)
    recorded = load_json(altered / "environment.json")
    recorded["freetype"] = "different-version"
    write_json(altered / "environment.json", recorded)
    manifest = load_json(altered / "manifest.json")
    manifest["generator"]["environment_sha256"] = sha256(altered / "environment.json")
    write_json(altered / "manifest.json", manifest)
    output = tmp_path / "must_not_exist"
    report = replay_tool.reproduce(altered, output)
    assert report["status"] == "fail"
    assert report["environment"]["match"] is False
    assert "freetype" in report["environment"]["differences"]
    assert report["pages_reproduced"] == 0
    assert not output.exists()


def test_insufficient_disk_is_refused_before_output_creation(
    two_pages, tmp_path, replay_tool, monkeypatch
):
    monkeypatch.setattr(
        replay_tool.shutil, "disk_usage", lambda _: SimpleNamespace(free=499_999_999)
    )
    output = tmp_path / "must_not_exist"
    report = replay_tool.reproduce(two_pages, output)
    assert report["status"] == "fail"
    assert "Espace libre insuffisant" in report["errors"][0]
    assert not output.exists()


@pytest.mark.parametrize("name,value", [("width", 800.0), ("seed", True), ("columns", False)])
def test_config_does_not_coerce_numbers(replay_tool, name, value):
    config = {"schema_version": "0.2.0", "pages": 2, "render": Config().as_dict()}
    config["render"][name] = value
    with pytest.raises(ValueError):
        replay_tool.strict_config(config)


def test_report_inside_source_is_refused_without_writes(two_pages, tmp_path, replay_tool):
    before = snapshot(two_pages)
    output = tmp_path / "must_not_exist"
    report = replay_tool.reproduce(two_pages, output, two_pages / "report.json")
    assert report["status"] == "fail"
    assert "hors du lot source" in report["errors"][0]
    assert not output.exists()
    assert snapshot(two_pages) == before


def test_extra_unlisted_page_is_not_silently_omitted(two_pages, tmp_path, replay_tool):
    altered = tmp_path / "extra_source"
    shutil.copytree(two_pages, altered)
    (altered / "pages/unlisted.json").write_text("{}\n", encoding="utf-8")
    output = tmp_path / "must_not_exist"
    report = replay_tool.reproduce(altered, output)
    assert report["status"] == "fail"
    assert "Inventaire pages" in report["errors"][0]
    assert report["pages_reproduced"] == 0
    assert not output.exists()


def test_byte_mismatch_is_reported_and_generated_copies_are_retained(
    two_pages, tmp_path, replay_tool, monkeypatch
):
    real_render = replay_tool.render_page

    def changed_annotation(*args, **kwargs):
        page = real_render(*args, **kwargs)
        page = deepcopy(page)
        page["provenance"]["parameters"]["test_extra_field"] = "deliberate mismatch"
        return page

    monkeypatch.setattr(replay_tool, "render_page", changed_annotation)
    output = tmp_path / "mismatch"
    report = replay_tool.reproduce(two_pages, output)
    assert report["status"] == "fail"
    assert report["files_compared"] == 4
    assert report["pages_reproduced"] == 2
    assert len(report["mismatches"]) == 2
    assert all(item["kind"] == "page_json" for item in report["mismatches"])
    assert len(list((output / "pages").glob("*.json"))) == 2
    assert len(list((output / "images").glob("*.png"))) == 2


def test_cli_returns_nonzero_on_refusal(two_pages, tmp_path, replay_tool, capsys):
    output = tmp_path / "occupied"
    output.mkdir()
    (output / "keep").write_text("keep", encoding="utf-8")
    assert replay_tool.main([str(two_pages), "--output", str(output)]) == 1
    assert '"status": "fail"' in capsys.readouterr().out
