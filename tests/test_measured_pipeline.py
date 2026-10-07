"""Small real measured lots, self-contained replay and CLI boundary checks."""

from collections import Counter
from copy import deepcopy
import importlib.util
import json

import numpy as np
from PIL import Image
import pytest

from mille_feuilles import cli, pipeline
from mille_feuilles.degrade import load_profile
from mille_feuilles.io import ROOT, sha256
from mille_feuilles.render import Config, PROFILE_MEASURED
from mille_feuilles.validation import load_json, validate_dataset


def snapshot(root):
    return {path.relative_to(root).as_posix(): sha256(path)
            for path in root.rglob("*") if path.is_file()}


@pytest.fixture(scope="module")
def measured_lots(tmp_path_factory):
    root = tmp_path_factory.mktemp("measured_pipeline")
    environment = pipeline.environment()
    git = pipeline.git_state()
    lots = {}
    # Freeze only real provenance observations while other agents edit files.
    # Composition, exports, validation and all output serialization remain real.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pipeline, "environment", lambda: deepcopy(environment))
        patch.setattr(pipeline, "git_state", lambda: git)
        for name in ("identity", "controlled-v1"):
            config = Config(width=800, height=1100, columns=4, seed=731,
                            degradation_profile=load_profile(name))
            source, replay = root / name, root / f"{name}-replay"
            report = pipeline.build_dataset(source, config, count=1, jobs=1)
            assert report["status"] == "pass", report["errors"]
            before = snapshot(source)
            # Read the portable profile from the lot, not the installed preset.
            saved_config = load_json(source / "config.json")["render"]
            saved_config["degradation_profile"] = load_profile(
                source / "provenance/degradation-profile.json"
            )
            repeated = pipeline.build_dataset(
                replay, Config(**saved_config), count=1, jobs=1, asset_source=source
            )
            assert repeated["status"] == "pass", repeated["errors"]
            assert snapshot(source) == before
            lots[name] = {"source": source, "replay": replay, "config": config, "report": report}
    return {"lots": lots, "environment": environment}


@pytest.mark.parametrize("name", ["identity", "controlled-v1"])
def test_measured_profile_config_and_manifest_are_pinned(measured_lots, name):
    fixture = measured_lots["lots"][name]
    root, config = fixture["source"], fixture["config"]
    manifest = load_json(root / "manifest.json")
    stored_config = load_json(root / "config.json")
    profile_ref = manifest["extensions"]["mf:degradation_profile"]
    assert manifest["profile"] == PROFILE_MEASURED
    assert profile_ref == {
        "path": "provenance/degradation-profile.json",
        "sha256": sha256(root / "provenance/degradation-profile.json"),
    }
    assert load_json(root / profile_ref["path"]) == config.degradation_profile
    assert stored_config["render"] == config.as_dict()
    assert stored_config["pages"] == 1
    inventory = {item["path"]: item["sha256"] for item in manifest["artifacts"]}
    assert inventory[profile_ref["path"]] == profile_ref["sha256"]
    assert manifest["config"]["sha256"] == inventory["config.json"] == sha256(root / "config.json")
    assert all(check["status"] == "pass" for check in fixture["report"]["checks"])
    assert validate_dataset(root)["status"] == "pass"


@pytest.mark.parametrize("name", ["identity", "controlled-v1"])
def test_diagnostics_masks_labels_statistics_and_severity_are_delivered(measured_lots, name):
    root = measured_lots["lots"][name]["source"]
    manifest = load_json(root / "manifest.json")
    inventory = {item["path"]: item["sha256"] for item in manifest["artifacts"]}
    assert len(manifest["pages"]) == 1
    page = load_json(root / manifest["pages"][0]["path"])
    ref = page["extensions"]["mf:diagnostics"]
    assert ref["version"] == "1"
    assert ref["path"] == f"qa/diagnostics/{page['page_id']}.json"
    assert ref["mask_path"] == f"qa/masks/{page['page_id']}.png"
    for relative, expected in ((ref["path"], ref["sha256"]),
                               (ref["mask_path"], ref["mask_sha256"]),
                               (page["image"]["path"], page["image"]["sha256"])):
        assert inventory[relative] == expected == sha256(root / relative)
    diagnostic = load_json(root / ref["path"])
    assert diagnostic["inputs"] == {
        "image": {"path": page["image"]["path"], "sha256": page["image"]["sha256"]},
        "mask": {"path": ref["mask_path"], "sha256": ref["mask_sha256"]},
    }
    with Image.open(root / ref["mask_path"]) as mask:
        assert mask.mode == "1" and mask.size == (800, 1100)
        assert int(np.asarray(mask, dtype=bool).sum()) == diagnostic["page"]["ink_pixels"]
    with Image.open(root / page["image"]["path"]) as image:
        assert image.mode == "L" and image.size == (800, 1100)
    words = {word["id"]: word["legibility"] for word in page["words"]}
    assert words == {key: item["legibility"] for key, item in diagnostic["words"].items()}
    counts = Counter(words.values())
    expected_counts = {label: counts[label] for label in ("readable", "uncertain", "illegible")}
    assert diagnostic["page"]["legibility"] == expected_counts
    stats = load_json(root / "qa/statistics.json")
    measured = stats["measured_degradations"]
    assert stats["words"] == sum(expected_counts.values()) > 100
    assert measured == {
        "profile": name, "calibrated": False, "legibility_method": "heuristic-v1",
        "legibility": expected_counts,
        "pages": [{"page_id": page["page_id"], **diagnostic["page"]}],
    }
    assert inventory["qa/statistics.json"] == sha256(root / "qa/statistics.json")
    assert inventory["qa/severity_00.jpg"] == sha256(root / "qa/severity_00.jpg")
    with Image.open(root / "qa/severity_00.jpg") as sheet:
        assert sheet.format == "JPEG" and sheet.mode == "RGB" and sheet.size == (400, 580)


@pytest.mark.parametrize("name", ["identity", "controlled-v1"])
def test_same_profile_replays_complete_lot_from_its_own_assets(measured_lots, name):
    fixture = measured_lots["lots"][name]
    comparison = pipeline.compare_lots(fixture["source"], fixture["replay"])
    assert comparison["status"] == "pass", comparison
    assert snapshot(fixture["source"]) == snapshot(fixture["replay"])


def test_reproduce_pilot_replays_measured_image_and_canonical_json(
    measured_lots, tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "measured_reproduce_pilot", ROOT / "tools/reproduce_pilot.py"
    )
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    monkeypatch.setattr(tool, "environment", lambda: deepcopy(measured_lots["environment"]))
    root = measured_lots["lots"]["controlled-v1"]["source"]
    before = snapshot(root)
    output = tmp_path / "measured-reproduced"
    report_path = tmp_path / "reproduction.json"
    report = tool.reproduce(root, output, report_path)
    assert report["status"] == "pass", report
    assert report["pages_expected"] == report["pages_reproduced"] == 1
    assert report["files_compared"] == 2
    assert report["mismatches"] == report["errors"] == []
    assert report["environment"]["match"] is True
    assert load_json(report_path) == report
    for relative in ("images/mf_0000.png", "pages/mf_0000.json",
                     "qa/masks/mf_0000.png", "qa/diagnostics/mf_0000.json"):
        assert (root / relative).read_bytes() == (output / relative).read_bytes()
    assert snapshot(root) == before


@pytest.mark.parametrize("mode", ["clean", "mixed"])
def test_cli_refuses_explicit_legacy_mode_with_measured_profile_before_build(
    tmp_path, monkeypatch, capsys, mode
):
    def forbidden_build(*args, **kwargs):
        pytest.fail("CLI must reject conflicting flags before building any page")

    monkeypatch.setattr(cli, "build_dataset", forbidden_build)
    output = tmp_path / "must-not-exist"
    with pytest.raises(SystemExit) as caught:
        cli.main(["generate", "--output", str(output), "--degradation", mode,
                  "--degradation-profile", "identity"])
    assert caught.value.code == 2
    error = capsys.readouterr().err
    assert {"--degradation-profile", "--degradation"} <= set(error.replace(":", " ").split())
    assert not output.exists()


@pytest.mark.parametrize("kind", ["unknown_name", "malformed_json"])
def test_cli_refuses_bad_profile_before_build(tmp_path, monkeypatch, capsys, kind):
    def forbidden_build(*args, **kwargs):
        pytest.fail("CLI must validate the profile before building any page")

    monkeypatch.setattr(cli, "build_dataset", forbidden_build)
    source = "profile-does-not-exist"
    if kind == "malformed_json":
        path = tmp_path / "bad-profile.json"
        path.write_text('{"name":', encoding="utf-8")
        source = str(path)
    output = tmp_path / "must-not-exist"
    code = cli.main(["generate", "--output", str(output), "--degradation-profile", source])
    assert code != 0
    assert "Profil de dégradation" in capsys.readouterr().err
    assert not output.exists()


def test_cli_generates_one_measured_page(tmp_path, capsys):
    output = tmp_path / "cli-measured"
    code = cli.main([
        "generate", "--output", str(output), "--pages", "1", "--width", "800",
        "--height", "1100", "--columns", "4", "--seed", "731",
        "--degradation-profile", "controlled-v1",
    ])
    captured = capsys.readouterr()
    assert code == 0, captured.err + captured.out
    result = json.loads(captured.out)
    assert result["status"] == "pass" and result["statistics"]["pages"] == 1
    assert "1/1 pages" in captured.err
    manifest = load_json(output / "manifest.json")
    assert manifest["profile"] == PROFILE_MEASURED and len(manifest["pages"]) == 1
    assert load_json(output / "config.json")["render"]["degradation_profile"] == load_profile("controlled-v1")
