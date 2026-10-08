"""Content-profile boundaries with tiny original texts and no raster generation."""

from copy import deepcopy
import importlib.util
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from mille_feuilles import cli, content, exports, partition, pipeline, render, validation
from mille_feuilles.degrade import load_profile
from mille_feuilles.io import ROOT, sha256, write_json
from mille_feuilles.render import Config, PROFILE_LAYOUT, SCHEMA_VERSION
from mille_feuilles.validation import load_json


def active_config(**overrides):
    return Config(**{"width": 800, "height": 1100, "columns": 4,
                     "layout_profile": PROFILE_LAYOUT, "degradation_profile": load_profile("identity"),
                     "content_profile": content.PROFILE, **overrides})


@pytest.fixture(scope="module")
def reproduce():
    spec = importlib.util.spec_from_file_location("content_reproduce_pilot", ROOT / "tools/reproduce_pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_raster_or_git(monkeypatch, reproduce):
    def forbidden(*args, **kwargs):
        raise AssertionError("Content boundary tests must not render, open images or invoke Git")

    for module in (pipeline, render, reproduce):
        monkeypatch.setattr(module, "render_page", forbidden)
    for name in ("new", "open", "fromarray", "frombytes"):
        monkeypatch.setattr(Image, name, forbidden)
    monkeypatch.setattr(pipeline, "git_state", lambda: ("0" * 40, False))


@pytest.fixture
def texts(tmp_path):
    source = tmp_path / "source"
    original = load_json(ROOT / "assets/catalog.json")
    templates = {asset["metadata"]["role"]: asset for asset in original["assets"] if asset["kind"] == "text"}
    assets = []
    for identity, role, value in (
        ("body_bad", "body", "Une seule unité originale."),
        ("body_good", "body", "Première unité originale.\n\nDeuxième unité originale.\n\nTroisième unité originale."),
        ("title", "title", None), ("advert", "advertisement", None),
    ):
        asset = deepcopy(templates[role])
        asset.update(id=identity, path=f"assets/texts/{identity}.txt")
        asset["metadata"].update(source_document_id=f"document_{identity}", source_group_id=f"group_{identity}")
        if value is not None:
            path = source / asset["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
            asset["sha256"] = sha256(path)
        # Non-body files deliberately do not exist: preflight must not open them.
        assets.append(asset)
    write_json(source / "assets/catalog.json", {"schema_version": SCHEMA_VERSION, "assets": assets})
    return source, assets


def sample_page():
    return {
        "page_id": "mf_0000", "words": [], "lines": [],
        "blocks": [{"id": "h", "category": "titre"}, {"id": "b1", "category": "texte"},
                   {"id": "b2", "category": "texte"}, {"id": "ad", "category": "annonce"}],
        "articles": [
            {"id": "article", "block_ids": ["h", "b1", "b2"], "extensions": {
                "mf:source_sequence": {"version": "1", "asset_id": "body_good", "start": 0,
                                       "end": 51, "unit_range": [0, 2]}}},
            {"id": "advert_article", "block_ids": ["ad"]},
        ],
        "provenance": {"parameters": {"columns": 4, "degradation": "clean", "content_profile": content.PROFILE},
                       "text_spans": [
                           {"article_id": "article", "asset_id": "body_good", "start": 0, "end": 51,
                            "source_document_id": "document_body_good", "block_ids": ["b1", "b2"]},
                           {"article_id": "article", "asset_id": "title", "start": 0, "end": 10,
                            "source_document_id": "document_title", "block_ids": ["h"]},
                           {"article_id": "advert_article", "asset_id": "advert", "start": 0, "end": 10,
                            "source_document_id": "document_advert", "block_ids": ["ad"]},
                       ]},
    }


def test_preflight_indexes_only_selected_body_and_reports_ineligible_sources(texts):
    source, assets = texts
    selected = {asset["id"] for asset in assets}
    report = pipeline.preflight_content_profile(source, content.PROFILE, selected)
    assert report == {"version": "1", "profile": content.PROFILE, "calibrated": False,
                      "documents": [
                          {"asset_id": asset["id"], "source_document_id": asset["metadata"]["source_document_id"],
                           "sha256": asset["sha256"], "unit_count": count, "eligible": count >= 2,
                           "reason": None if count >= 2 else "fewer_than_two_body_units"}
                          for asset, count in zip(assets[:2], (1, 3))]}


def test_eligible_document_in_excluded_partition_cannot_satisfy_preflight(texts, tmp_path, monkeypatch):
    source, _ = texts
    selected = {"body_bad", "title", "advert"}
    monkeypatch.setattr(partition, "load_partition", lambda root, name: selected)
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="at least two units"):
        pipeline.build_dataset(output, active_config(partition="train"), asset_source=source)
    assert not output.exists()


def test_selected_body_sha_failure_precedes_mkdir(texts, tmp_path):
    source, assets = texts
    (source / assets[1]["path"]).write_text("Texte modifié.\n\nAutre unité.", encoding="utf-8")
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        pipeline.build_dataset(output, active_config(), asset_source=source)
    assert not output.exists()


@pytest.mark.parametrize("profile", [None, content.PROFILE])
def test_cli_forwards_explicit_content_profile_without_adding_legacy_serialization(tmp_path, monkeypatch, capsys, profile):
    seen = []

    def build(output, config, count, jobs, **kwargs):
        seen.append(config)
        return {"status": "pass"}

    monkeypatch.setattr(cli, "build_dataset", build)
    arguments = ["generate", "--output", str(tmp_path / "untouched")]
    if profile:
        arguments += ["--layout-profile", PROFILE_LAYOUT, "--degradation-profile", "identity",
                      "--content-profile", profile]
    assert cli.main(arguments) == 0
    assert seen[0].content_profile == profile
    assert ("content_profile" in seen[0].as_dict()) == (profile is not None)
    assert json.loads(capsys.readouterr().out)["status"] == "pass"


@pytest.mark.parametrize("options", [[], ["--degradation-profile", "identity"]])
def test_cli_content_requires_layout_before_build(tmp_path, monkeypatch, capsys, options):
    monkeypatch.setattr(cli, "build_dataset", lambda *args, **kwargs: pytest.fail("invalid config reached build"))
    output = tmp_path / "absent"
    assert cli.main(["generate", "--output", str(output), "--content-profile", content.PROFILE, *options]) == 2
    assert capsys.readouterr().out == ""
    assert not output.exists()


def test_cli_unknown_content_profile_is_argparse_refusal(tmp_path, capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main(["generate", "--output", str(tmp_path / "absent"), "--content-profile", "invented"])
    assert caught.value.code == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("config", [Config(), active_config(content_profile=None), active_config()])
def test_reproduction_config_preserves_active_option_and_accepts_old_omission(reproduce, config):
    value = {"schema_version": SCHEMA_VERSION, "render": config.as_dict(), "pages": 1}
    restored, count = reproduce.strict_config(value)
    assert count == 1 and restored == config
    assert restored.as_dict() == value["render"]


def test_statistics_count_committed_body_sequences_and_actual_documents():
    page = sample_page()
    second = deepcopy(page)
    second["articles"][0]["extensions"]["mf:source_sequence"]["unit_range"] = [2, 5]
    assert pipeline.content_statistics([page, second]) == {
        "profile": content.PROFILE, "calibrated": False, "articles": 2,
        "units_per_article": {"2": 1, "3": 1}, "body_documents": {"document_body_good": 2},
    }


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "offset", "blocks", "document", "unit_count"])
def test_statistics_refuse_unreconciled_sequence_claims(mutation):
    page = sample_page()
    spans = page["provenance"]["text_spans"]
    if mutation == "missing":
        spans.pop(0)
    elif mutation == "duplicate":
        spans.append(deepcopy(spans[0]))
    elif mutation == "offset":
        spans[0]["end"] += 1
    elif mutation == "blocks":
        spans[0]["block_ids"] = ["b1"]
    elif mutation == "document":
        spans[0]["source_document_id"] = ""
    else:
        page["articles"][0]["extensions"]["mf:source_sequence"]["unit_range"] = [0, 1]
    with pytest.raises(ValueError):
        pipeline.content_statistics([page])


@pytest.mark.parametrize("enabled", [False, True])
def test_pipeline_serializes_receipt_and_statistics_only_when_enabled(texts, tmp_path, monkeypatch, enabled):
    """Assembly boundary only: real serialization, fake renderer and validators."""
    source, assets = texts
    target = tmp_path / "assembled"
    expected_receipt = pipeline.preflight_content_profile(source, content.PROFILE)

    def prepare(root, asset_source, selected, **kwargs):
        write_json(root / "assets.json", {"schema_version": SCHEMA_VERSION, "assets": assets})
        write_json(root / "assets/template.json", {"layout_options": {}})
        return assets

    def fake_render(config, index, registry, root):
        page = sample_page()
        if not enabled:
            del page["articles"][0]["extensions"]["mf:source_sequence"]
            del page["provenance"]["parameters"]["content_profile"]
        relative = "qa/diagnostics/mf_0000.json"
        page["extensions"] = {"mf:diagnostics": {"path": relative}}
        write_json(root / relative, {"page_id": page["page_id"], "page": {
            "legibility": {"illegible": 0, "uncertain": 0}, "contrast": 1}})
        return page

    monkeypatch.setattr(pipeline, "prepare_assets", prepare)
    monkeypatch.setattr(pipeline, "render_page", fake_render)
    monkeypatch.setattr(pipeline, "environment", lambda: {"test": "no raster assembly boundary"})
    monkeypatch.setattr(pipeline.shutil, "disk_usage", lambda path: SimpleNamespace(free=10**12))
    monkeypatch.setattr(pipeline, "overlay", lambda *args: None)
    monkeypatch.setattr(pipeline, "contact_sheets", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "layout_statistics", lambda *args: {})
    monkeypatch.setattr(exports, "export_page", lambda *args: None)
    monkeypatch.setattr(exports, "export_coco", lambda *args: None)
    monkeypatch.setattr(validation, "validate_page", lambda page: [])
    monkeypatch.setattr(validation, "validate_dataset", lambda root: {"status": "pass"})
    if not enabled:
        monkeypatch.setattr(pipeline, "preflight_content_profile", lambda *args: pytest.fail("legacy path called content preflight"))
    result = pipeline.build_dataset(target, active_config(content_profile=content.PROFILE if enabled else None),
                                    asset_source=source)
    manifest, config = load_json(target / "manifest.json"), load_json(target / "config.json")
    assert ("content_profile" in config["render"]) == enabled
    assert ("mf:content_profile" in manifest["extensions"]) == enabled
    assert ("content" in result["statistics"]) == enabled
    if enabled:
        assert manifest["extensions"]["mf:content_profile"] == expected_receipt
        assert result["statistics"]["content"] == pipeline.content_statistics([sample_page()])


@pytest.mark.parametrize("profile_active,receipt_present,receipt_ok", [
    (True, True, True), (True, True, False), (False, True, False), (False, False, True),
])
def test_reproduction_keeps_content_option_and_checks_receipt_before_output(
    texts, tmp_path, monkeypatch, reproduce, profile_active, receipt_present, receipt_ok
):
    """Opaque byte marker stands for PNG; no validity or raster claim is made."""
    source, assets = texts
    target = tmp_path / "replayed"
    config = active_config() if profile_active else active_config(content_profile=None)
    env = {"test": "metadata-only reproduction boundary"}
    write_json(source / "config.json", {"schema_version": SCHEMA_VERSION, "render": config.as_dict(), "pages": 1})
    write_json(source / "environment.json", env)
    write_json(source / "assets.json", {"schema_version": SCHEMA_VERSION, "assets": assets})
    marker = source / "images/mf_0000.png"
    marker.parent.mkdir()
    marker.write_bytes(b"opaque bytes; not an image")
    page = {"page_id": "mf_0000", "image": {"path": "images/mf_0000.png", "sha256": sha256(marker)}}
    write_json(source / "pages/mf_0000.json", page)

    def reference(relative):
        return {"path": relative, "sha256": sha256(source / relative)}

    receipt = pipeline.preflight_content_profile(source, content.PROFILE)
    if not receipt_ok:
        receipt["documents"][0]["unit_count"] += 1
    write_json(source / "manifest.json", {
        "schema_version": SCHEMA_VERSION, "generator": {"commit": "test", "dirty": False,
            "environment_path": "environment.json", "environment_sha256": sha256(source / "environment.json")},
        "config": reference("config.json"), "assets": reference("assets.json"),
        "artifacts": [reference("assets/catalog.json")],
        "pages": [{"id": "mf_0000", **reference("pages/mf_0000.json")}],
        "extensions": ({"mf:content_profile": receipt} if receipt_present else {}),
    })
    before = {path.relative_to(source).as_posix(): sha256(path) for path in source.rglob("*") if path.is_file()}
    seen = []

    def prepare(root, asset_source, **kwargs):
        write_json(root / "assets.json", load_json(source / "assets.json"))
        return assets

    def fake_render(restored, index, registry, root):
        seen.append(restored.content_profile)
        output_image = root / "images/mf_0000.png"
        output_image.parent.mkdir()
        output_image.write_bytes(marker.read_bytes())
        return deepcopy(page)

    monkeypatch.setattr(reproduce, "environment", lambda: deepcopy(env))
    monkeypatch.setattr(reproduce, "validate_partition_receipt", lambda *args: [])
    monkeypatch.setattr(validation, "validate_dataset", lambda root: {"status": "pass"})
    monkeypatch.setattr(reproduce.shutil, "disk_usage", lambda path: SimpleNamespace(free=10**12))
    monkeypatch.setattr(reproduce, "prepare_assets", prepare)
    monkeypatch.setattr(reproduce, "render_page", fake_render)
    result = reproduce.reproduce(source, target)
    assert result["status"] == ("pass" if receipt_ok else "fail"), result
    # A passing replay renders with the restored option, including the legacy None; a refusal renders nothing.
    assert seen == ([content.PROFILE if profile_active else None] if receipt_ok else [])
    assert target.exists() == receipt_ok
    if receipt_ok:
        assert result["files_compared"] == 2
    else:
        assert any("profil de contenu" in error.lower() for error in result["errors"])
    assert {path.relative_to(source).as_posix(): sha256(path) for path in source.rglob("*") if path.is_file()} == before
