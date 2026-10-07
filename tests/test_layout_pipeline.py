"""Portable layout integration and compatibility with the frozen lot-3 code.

The legacy reference is loaded from Git blobs in memory, without a checkout or
an external test runner. Boundary tests forbid raster work; the shared compact
integration fixture renders only two one-page lots, with a 25 MB disk budget.
"""

from copy import deepcopy
import importlib
import importlib.abc
import importlib.util
import json
import shutil
import subprocess
import sys
from types import SimpleNamespace

from PIL import Image
import pytest
import test_partitioned_pipeline

from mille_feuilles import cli, pipeline, render
from mille_feuilles.degrade import load_profile
from mille_feuilles.io import ROOT, sha256, write_json
from mille_feuilles.layout import DEFAULT_OPTIONS, check_options
from mille_feuilles.render import Config, PROFILE_LAYOUT, SCHEMA_VERSION
from mille_feuilles.validation import load_json


BASELINE_COMMIT = "cb24e39e42d6c7519a32f6b70bcbccced6e13f36"
ASSET_BUDGET = 5 * 1024 * 1024
INTEGRATION_BUDGET = 25_000_000
# Reuse the original, rights-documented multi-document bundle without invoking
# that module's independent legacy rendering fixture.
partitioned_bundle = test_partitioned_pipeline.partitioned_bundle


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): (path.stat().st_size, sha256(path))
        for path in sorted(root.rglob("*")) if path.is_file()
    }


class GitBaseline(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Load an isolated package from the documented Git baseline, without writes."""

    prefix = "mf_layout_legacy_baseline"

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self.prefix or fullname.startswith(self.prefix + "."):
            return importlib.util.spec_from_loader(fullname, self, is_package=fullname == self.prefix)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        is_package = module.__name__ == self.prefix
        relative = "src/mille_feuilles/" + (
            "__init__.py" if is_package
            else module.__name__.split(".", 1)[1].replace(".", "/") + ".py"
        )
        source = subprocess.check_output(
            ["git", "show", f"{BASELINE_COMMIT}:{relative}"], cwd=ROOT,
        )
        # Resource lookup still uses this checkout's builtin assets and schemas;
        # every Python module of the reference package comes from the Git blob.
        module.__file__ = str(ROOT / relative)
        if is_package:
            module.__path__ = [str(ROOT / "src/mille_feuilles")]
        exec(compile(source, f"git:{BASELINE_COMMIT}:{relative}", "exec"), module.__dict__)


@pytest.fixture(scope="module")
def baseline():
    loader = GitBaseline()
    sys.meta_path.insert(0, loader)
    try:
        yield SimpleNamespace(
            render=importlib.import_module(f"{loader.prefix}.render"),
            pipeline=importlib.import_module(f"{loader.prefix}.pipeline"),
        )
    finally:
        sys.meta_path.remove(loader)
        for name in list(sys.modules):
            if name == loader.prefix or name.startswith(loader.prefix + "."):
                del sys.modules[name]


@pytest.fixture(scope="module")
def reproduce():
    spec = importlib.util.spec_from_file_location(
        "layout_reproduce_pilot", ROOT / "tools/reproduce_pilot.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def forbid_rasters_in_boundary_tests(request, monkeypatch, reproduce):
    if "layout_lots" in request.fixturenames:
        return

    def forbidden(*args, **kwargs):
        raise AssertionError("Boundary tests must not render or open/create images")

    for module in (render, pipeline, reproduce):
        monkeypatch.setattr(module, "render_page", forbidden)
    for name in ("new", "open", "fromarray", "frombytes"):
        monkeypatch.setattr(Image, name, forbidden)
    monkeypatch.setattr(render.Composer, "__init__", forbidden)


@pytest.mark.parametrize("legacy_args", [[], ["--degradation", "clean"]])
def test_cli_refuses_layout_without_measured_profile_before_build_or_output(
    tmp_path, monkeypatch, capsys, legacy_args,
):
    def forbidden_build(*args, **kwargs):
        pytest.fail("CLI must reject the inconsistent options before build_dataset")

    monkeypatch.setattr(cli, "build_dataset", forbidden_build)
    output = tmp_path / "must-not-exist"
    code = cli.main([
        "generate", "--output", str(output), "--layout-profile", PROFILE_LAYOUT,
        *legacy_args,
    ])
    captured = capsys.readouterr()
    assert code == 2
    assert "degradation_profile" in captured.err or "--degradation-profile" in captured.err
    assert captured.out == ""
    assert not output.exists()


def test_cli_refuses_unknown_layout_before_build_or_output(tmp_path, monkeypatch, capsys):
    def forbidden_build(*args, **kwargs):
        pytest.fail("Unknown layout must not reach build_dataset")

    monkeypatch.setattr(cli, "build_dataset", forbidden_build)
    output = tmp_path / "must-not-exist"
    with pytest.raises(SystemExit) as error:
        cli.main([
            "generate", "--output", str(output), "--layout-profile", "layout_typo",
            "--degradation-profile", "identity",
        ])
    assert error.value.code == 2
    assert "--layout-profile" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize("profile_name", ["identity", "controlled-v1"])
def test_cli_forwards_layout_and_all_requested_options_to_fake_build(
    tmp_path, monkeypatch, capsys, profile_name,
):
    observed = []

    def fake_build(output, config, count, jobs, *, progress, asset_source):
        config.validate()
        observed.append((output, config, count, jobs, asset_source))
        progress("boundary reached without generation")
        return {"status": "pass", "boundary": "build_dataset"}

    monkeypatch.setattr(cli, "build_dataset", fake_build)
    output, source = tmp_path / "not-created", tmp_path / "source-not-read"
    code = cli.main([
        "generate", "--output", str(output), "--assets-root", str(source),
        "--pages", "2", "--jobs", "2", "--width", "800", "--height", "1100",
        "--dpi", "45", "--columns", "4", "--seed", "731", "--partition", "train",
        "--layout-profile", PROFILE_LAYOUT, "--degradation-profile", profile_name,
    ])
    assert code == 0
    assert len(observed) == 1
    called_output, config, count, jobs, asset_source = observed[0]
    assert (called_output, count, jobs, asset_source) == (output, 2, 2, source)
    assert config.as_dict() == {
        "width": 800, "height": 1100, "dpi": 45, "columns": 4,
        "degradation": "mixed", "seed": 731, "partition": "train",
        "degradation_profile": load_profile(profile_name), "layout_profile": PROFILE_LAYOUT,
    }
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "pass", "boundary": "build_dataset"}
    assert "boundary reached" in captured.err
    assert not output.exists() and not source.exists()


@pytest.mark.parametrize("profile_name", [None, "identity"])
def test_config_as_dict_and_serialization_remain_byte_compatible_without_layout(
    tmp_path, baseline, profile_name,
):
    options = {"width": 800, "height": 1100, "dpi": 45, "columns": 4, "seed": 731}
    if profile_name is not None:
        options["degradation_profile"] = load_profile(profile_name)
    old = baseline.render.Config(**deepcopy(options))
    current = Config(**deepcopy(options))
    old.validate()
    current.validate()
    assert current.as_dict() == old.as_dict()
    assert "layout_profile" not in current.as_dict()
    if profile_name is None:
        assert "degradation_profile" not in current.as_dict()
    old_path, current_path = tmp_path / "old.json", tmp_path / "current.json"
    write_json(old_path, {"schema_version": SCHEMA_VERSION, "render": old.as_dict(), "pages": 1})
    write_json(current_path, {
        "schema_version": SCHEMA_VERSION, "render": current.as_dict(), "pages": 1,
    })
    assert current_path.read_bytes() == old_path.read_bytes()


@pytest.mark.parametrize("profile_name", [None, "identity"])
def test_strict_config_accepts_pre_layout_files(reproduce, baseline, profile_name):
    options = {"width": 800, "height": 1100, "columns": 4}
    if profile_name:
        options["degradation_profile"] = load_profile(profile_name)
    previous = baseline.render.Config(**options).as_dict()
    assert "layout_profile" not in previous
    config, count = reproduce.strict_config({
        "schema_version": SCHEMA_VERSION, "render": previous, "pages": 1,
    })
    assert count == 1 and config.layout_profile is None
    assert config.as_dict() == previous


@pytest.mark.parametrize("mutation", ["unknown_render", "unknown_root", "missing_width"])
def test_strict_config_keeps_unknown_and_required_field_guards(reproduce, mutation):
    value = {"schema_version": SCHEMA_VERSION, "render": Config().as_dict(), "pages": 1}
    if mutation == "unknown_render":
        value["render"]["layout_options_typo"] = {}
    elif mutation == "unknown_root":
        value["unexpected"] = None
    else:
        del value["render"]["width"]
    with pytest.raises(ValueError, match="configuration|incomplets|inconnus"):
        reproduce.strict_config(value)


def test_strict_config_roundtrips_explicit_layout_and_measured_profile(reproduce):
    original = Config(
        width=800, height=1100, columns=4,
        degradation_profile=load_profile("identity"), layout_profile=PROFILE_LAYOUT,
    )
    actual, count = reproduce.strict_config({
        "schema_version": SCHEMA_VERSION, "render": original.as_dict(), "pages": 1,
    })
    assert count == 1 and actual.as_dict() == original.as_dict()


@pytest.mark.parametrize("layout", ["unknown", True, {}])
def test_strict_config_rejects_unknown_layout_values(reproduce, layout):
    parameters = Config(degradation_profile=load_profile("identity")).as_dict()
    parameters["layout_profile"] = layout
    with pytest.raises(ValueError, match="mise en page"):
        reproduce.strict_config({"schema_version": SCHEMA_VERSION, "render": parameters, "pages": 1})


def test_strict_config_refuses_layout_without_measured_profile(reproduce):
    parameters = Config().as_dict()
    parameters["layout_profile"] = PROFILE_LAYOUT
    with pytest.raises(ValueError, match="degradation_profile"):
        reproduce.strict_config({"schema_version": SCHEMA_VERSION, "render": parameters, "pages": 1})


@pytest.fixture(scope="module")
def asset_bundles(tmp_path_factory, baseline):
    # A conservative preflight includes all builtin assets, even unreferenced
    # verification scripts, plus room for four registries/templates/notices.
    source_bytes = sum(p.stat().st_size for p in (ROOT / "assets").rglob("*") if p.is_file())
    estimate = 4 * source_bytes + 128 * 1024
    if estimate >= ASSET_BUDGET:
        pytest.skip(f"Prepared asset tests exceed the 5 MiB allowance: {estimate} bytes")
    before = snapshot(ROOT / "assets")
    folder = tmp_path_factory.mktemp("asset_boundaries")
    paths = {name: folder / name for name in ("baseline", "v1", "v2", "v2-replay")}
    for path in paths.values():
        path.mkdir()
    registries = {"baseline": baseline.pipeline.prepare_assets(paths["baseline"], ROOT)}
    registries["v1"] = pipeline.prepare_assets(paths["v1"], ROOT)
    registries["v2"] = pipeline.prepare_assets(paths["v2"], ROOT, layout_profile=PROFILE_LAYOUT)
    registries["v2-replay"] = pipeline.prepare_assets(
        paths["v2-replay"], paths["v2"], layout_profile=PROFILE_LAYOUT,
    )
    written = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    assert written < ASSET_BUDGET, written
    assert snapshot(ROOT / "assets") == before
    assert not any(p.suffix.lower() in {".png", ".jpg", ".jpeg"} for p in folder.rglob("*"))
    return SimpleNamespace(paths=paths, registries=registries, written_bytes=written)


def test_prepare_assets_v1_is_byte_identical_to_cb24e39(asset_bundles):
    old, current = asset_bundles.paths["baseline"], asset_bundles.paths["v1"]
    assert asset_bundles.registries["v1"] == asset_bundles.registries["baseline"]
    assert snapshot(current) == snapshot(old)
    for relative in snapshot(old):
        assert (current / relative).read_bytes() == (old / relative).read_bytes(), relative


def test_prepare_assets_v2_has_consistent_template_options_rights_and_provenance(asset_bundles):
    root = asset_bundles.paths["v2"]
    registry = load_json(root / "assets.json")
    assert registry == {"schema_version": SCHEMA_VERSION, "assets": asset_bundles.registries["v2"]}
    templates = [a for a in registry["assets"] if a["kind"] == "template"]
    assert len(templates) == 1
    template = templates[0]
    assert template["id"] == "template_press_v2"
    assert template["source_uri"] == (
        f"urn:mille-feuilles:original-template:v{SCHEMA_VERSION}:template_press_v2"
    )
    assert template["sha256"] == sha256(root / template["path"])
    data = load_json(root / template["path"])
    assert (data["id"], data["profile"], data["calibrated"]) == (
        "template_press_v2", PROFILE_LAYOUT, False,
    )
    assert data["layout_options"] == check_options(deepcopy(DEFAULT_OPTIONS))
    assert "template_press_v1" not in {a["id"] for a in registry["assets"]}
    assert template["rights"]["status"] == "verified"
    assert template["rights"]["license"] == "CC0-1.0"
    assert template["rights"]["redistribution_allowed"] is True
    for evidence in template["metadata"]["evidence_files"]:
        assert evidence["sha256"] == sha256(root / evidence["path"])
    assert (root / "assets/catalog.json").read_bytes() == (ROOT / "assets/catalog.json").read_bytes()
    changed = {"assets.json", "assets/template.json"}
    old_inventory, new_inventory = snapshot(asset_bundles.paths["v1"]), snapshot(root)
    assert old_inventory.keys() == new_inventory.keys()
    assert {key for key in old_inventory if old_inventory[key] != new_inventory[key]} == changed


def test_prepare_assets_v2_replays_from_copied_bundle_without_source_changes(asset_bundles):
    source, replay = asset_bundles.paths["v2"], asset_bundles.paths["v2-replay"]
    assert snapshot(source) == snapshot(replay)
    assert asset_bundles.registries["v2"] == asset_bundles.registries["v2-replay"]


def test_prepare_assets_unknown_layout_refuses_before_any_output(tmp_path):
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="mise en page"):
        pipeline.prepare_assets(output, ROOT, layout_profile="unknown")
    assert not output.exists()


def stats_page(normal_size, *, lower_zone=False):
    """Minimal observed layout records for the public statistics boundary."""
    zones = [{"id": "main", "columns": [{}, {}, {}, {}]}]
    typography = {"main": {"normal_body_size": normal_size}}
    article = {
        "block_ids": ["main-text"],
        "extensions": {"mf:layout": {
            "zone_id": "main", "headline": None, "box": None,
            "small_body_requested": False, "small_body": False,
            "body_font_size": normal_size,
        }},
    }
    articles = [article]
    if lower_zone:
        zones.append({"id": "rez_de_chaussee", "columns": [{}, {}, {}]})
        typography["rez_de_chaussee"] = {"normal_body_size": 13}
        lower = deepcopy(article)
        lower["block_ids"] = ["lower-text"]
        lower["extensions"]["mf:layout"].update({
            "zone_id": "rez_de_chaussee", "body_font_size": 13,
        })
        articles.append(lower)
    return {
        "articles": articles, "lines": [],
        "provenance": {"parameters": {
            "layout": {"zones": zones}, "layout_typography": typography,
        }},
    }


def test_layout_statistics_distinguishes_requests_clamps_and_effective_small_body():
    pages = [stats_page(normal) for normal in (10, 11, 12)]
    # With ratio .82, the requested rounded sizes are 8, 9 and 10. The
    # renderer's minimum is 10: two requests clamp; only the first is inactive.
    for page, effective in zip(pages, (False, True, True)):
        page["articles"][0]["extensions"]["mf:layout"].update({
            "small_body_requested": True, "small_body": effective, "body_font_size": 10,
        })
    statistics = pipeline.layout_statistics(pages, {"small_body_ratio": 0.82})
    assert statistics["small_body_requests"] == 3
    assert statistics["small_body_articles"] == 2
    assert statistics["small_body_clamped"] == 2
    assert statistics["small_body_inactive"] == 1
    assert statistics["body_sizes"] == {"10": 3}


def test_layout_line_height_histograms_ignore_rotation_and_masthead_and_separate_zones():
    flat = stats_page(10, lower_zone=True)
    flat["lines"] = [
        {"block_id": "main-text", "polygon": [[0, 0], [200, 0], [200, 10], [0, 10]]},
        {"block_id": "main-text", "polygon": [[0, 20], [200, 20], [200, 30], [0, 30]]},
        {"block_id": "lower-text", "polygon": [[0, 40], [200, 40], [200, 53], [0, 53]]},
        {"block_id": "masthead", "polygon": [[0, 80], [400, 80], [400, 140], [0, 140]]},
    ]
    rotated = deepcopy(flat)
    # A genuine rigid rotation, cos(theta)=3/5, sin(theta)=4/5. The first
    # 200x10 rectangle has an AABB height of 166, while its own height stays 10.
    for line in rotated["lines"]:
        line["polygon"] = [[0.6*x - 0.8*y, 0.8*x + 0.6*y] for x, y in line["polygon"]]
    expected = {"main": {"10": 2}, "rez_de_chaussee": {"13": 1}}
    first = pipeline.layout_statistics([flat], {"small_body_ratio": 0.82})
    second = pipeline.layout_statistics([rotated], {"small_body_ratio": 0.82})
    assert first["line_heights_px"] == second["line_heights_px"] == expected
    assert first["line_height_bin_px"] == second["line_height_bin_px"] == 1
    assert first["zones"] == second["zones"] == {"main": 1, "rez_de_chaussee": 1}


def test_reproduce_forwards_layout_to_asset_preparation_before_render(
    tmp_path, monkeypatch, reproduce,
):
    """Exercise real preflight with tiny metadata; stop before raster work.

    The manifest's PNG entry points to an explicitly invalid opaque byte marker.
    This verifies orchestration only: image validity is deliberately delegated to
    validate_dataset, stubbed here, and is not claimed by this boundary test.
    """
    source, target = tmp_path / "metadata-source", tmp_path / "not-rendered"
    source.mkdir()
    config = Config(
        width=800, height=1100, columns=4,
        degradation_profile=load_profile("identity"), layout_profile=PROFILE_LAYOUT,
    )
    environment = {"test": "metadata-only; no renderer executed"}
    write_json(source / "config.json", {
        "schema_version": SCHEMA_VERSION, "render": config.as_dict(), "pages": 1,
    })
    write_json(source / "environment.json", environment)
    write_json(source / "assets.json", {"schema_version": SCHEMA_VERSION, "assets": []})
    write_json(source / "assets/catalog.json", {"schema_version": SCHEMA_VERSION, "assets": []})
    marker = source / "images/mf_0000.png"
    marker.parent.mkdir()
    marker.write_bytes(b"NOT AN IMAGE: metadata-only boundary fixture\n")
    write_json(source / "pages/mf_0000.json", {
        "page_id": "mf_0000",
        "image": {"path": "images/mf_0000.png", "sha256": sha256(marker)},
    })

    def reference(relative):
        return {"path": relative, "sha256": sha256(source / relative)}

    write_json(source / "manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "generator": {
            "commit": "metadata-fixture-only", "dirty": False,
            "environment_path": "environment.json",
            "environment_sha256": sha256(source / "environment.json"),
        },
        "config": reference("config.json"), "assets": reference("assets.json"),
        "artifacts": [reference("assets/catalog.json")],
        "pages": [{"id": "mf_0000", **reference("pages/mf_0000.json")}],
    })
    before = snapshot(source)
    observed = []

    def stop_at_preparation(output, asset_source, **kwargs):
        observed.append((output, asset_source, kwargs))
        raise RuntimeError("Intentional stop before rendering")

    monkeypatch.setattr(reproduce, "environment", lambda: deepcopy(environment))
    monkeypatch.setattr(reproduce, "validate_partition_receipt", lambda *args: [])
    monkeypatch.setattr("mille_feuilles.validation.validate_dataset", lambda *args: {"status": "pass"})
    monkeypatch.setattr(reproduce.shutil, "disk_usage", lambda *args: SimpleNamespace(free=10**12))
    monkeypatch.setattr(reproduce, "prepare_assets", stop_at_preparation)
    report = reproduce.reproduce(source, target)
    assert observed == [(target, source, {"layout_profile": PROFILE_LAYOUT})]
    assert report["status"] == "fail"
    assert report["pages_reproduced"] == report["files_compared"] == 0
    assert any("Intentional stop before rendering" in issue for issue in report["errors"])
    assert snapshot(source) == before
    assert target.exists() and list(target.iterdir()) == []


@pytest.fixture(scope="module")
def layout_lots(tmp_path_factory, reproduce, partitioned_bundle):
    """One partitioned compact page and its complete replay, shared by all consumers."""
    if shutil.disk_usage(tmp_path_factory.getbasetemp()).free <= 1024**3:
        pytest.skip("Compact layout integration requires more than 1 GiB free")
    folder = tmp_path_factory.mktemp("layout_pipeline")
    source, replay = folder / "source", folder / "replay"
    config = Config(
        width=800, height=1100, dpi=45, columns=4, seed=731,
        degradation_profile=load_profile("identity"), layout_profile=PROFILE_LAYOUT,
        partition="train",
    )
    bundle = partitioned_bundle["bundle"]
    bundle_before = snapshot(bundle)
    original_before = snapshot(partitioned_bundle["source"])
    environment, git_state = pipeline.environment(), pipeline.git_state()

    def check_budget():
        size = sum(
            path.stat().st_size
            for root in (folder, partitioned_bundle["root"])
            for path in root.rglob("*") if path.is_file()
        )
        assert size < INTEGRATION_BUDGET, f"Integration fixture exceeds 25 MB: {size} bytes"
        return size

    # Preserve the actual observed code/environment state across the replay.
    # Other development tests may run while files change; no clean provenance
    # is invented, and rendering, exports and validation remain unpatched.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pipeline, "environment", lambda: deepcopy(environment))
        patch.setattr(pipeline, "git_state", lambda: git_state)
        first = pipeline.build_dataset(source, config, count=1, jobs=1, asset_source=bundle)
        assert first["status"] == "pass", first["errors"]
        check_budget()
        before = snapshot(source)
        restored, count = reproduce.strict_config(load_json(source / "config.json"))
        second = pipeline.build_dataset(
            replay, restored, count=count, jobs=2, asset_source=source,
        )
        assert second["status"] == "pass", second["errors"]
        assert snapshot(source) == before
    written_bytes = check_budget()
    assert snapshot(bundle) == bundle_before
    assert snapshot(partitioned_bundle["source"]) == original_before
    return SimpleNamespace(
        source=source, replay=replay, config=config, reports=(first, second),
        written_bytes=written_bytes, partitioned_bundle=partitioned_bundle,
    )


def test_compact_layout_pipeline_delivers_profile_template_and_zone_statistics(layout_lots):
    root = layout_lots.source
    manifest = load_json(root / "manifest.json")
    page = load_json(root / manifest["pages"][0]["path"])
    registry = load_json(root / manifest["assets"]["path"])
    statistics = load_json(root / "qa/statistics.json")
    assert manifest["profile"] == page["profile"] == PROFILE_LAYOUT
    assert "_layout_v2_train_" in manifest["dataset_id"]
    assert page["provenance"]["template_id"] == "template_press_v2"
    template_asset = next(a for a in registry["assets"] if a["id"] == "template_press_v2")
    template = load_json(root / template_asset["path"])
    assert template["profile"] == PROFILE_LAYOUT
    assert template["layout_options"] == DEFAULT_OPTIONS
    assert template_asset["sha256"] == sha256(root / template_asset["path"])
    assert template_asset["id"] in page["provenance"]["asset_ids"]
    assert load_json(root / "config.json")["render"] == layout_lots.config.as_dict()
    profile_ref = manifest["extensions"]["mf:degradation_profile"]
    assert profile_ref["sha256"] == sha256(root / profile_ref["path"])
    assert load_json(root / profile_ref["path"]) == layout_lots.config.degradation_profile
    inventory = {entry["path"]: entry["sha256"] for entry in manifest["artifacts"]}
    for relative in ("assets/template.json", "qa/statistics.json", profile_ref["path"]):
        assert inventory[relative] == sha256(root / relative)
    diagnostics = page["extensions"]["mf:diagnostics"]
    assert inventory[diagnostics["path"]] == diagnostics["sha256"]
    assert inventory[diagnostics["mask_path"]] == diagnostics["mask_sha256"]
    assert statistics["pages"] == 1 and statistics["words"] == len(page["words"]) > 0
    observed = statistics["layout"]
    assert observed["profile"] == PROFILE_LAYOUT and observed["calibrated"] is False
    zones = page["provenance"]["parameters"]["layout"]["zones"]
    assert observed["zones"] == {zone["id"]: 1 for zone in zones}
    assert len(next(zone for zone in zones if zone["id"] == "main")["columns"]) == 4
    assert observed["line_height_bin_px"] == 1
    assert set(observed["line_heights_px"]) == {zone["id"] for zone in zones}
    body_articles = [a for a in page["articles"] if "mf:layout" in a.get("extensions", {})]
    assert sum(observed["body_sizes"].values()) == len(body_articles) > 0
    article_blocks = {block for article in body_articles for block in article["block_ids"]}
    article_lines = [line for line in page["lines"] if line["block_id"] in article_blocks]
    assert sum(sum(hist.values()) for hist in observed["line_heights_px"].values()) == len(article_lines)
    assert len(article_lines) < len(page["lines"]), "Masthead must remain outside zone histograms"
    assert all(check["status"] == "pass" for report in layout_lots.reports for check in report["checks"])


def test_compact_layout_pipeline_replays_complete_lot_from_its_copied_bundle(layout_lots):
    result = pipeline.compare_lots(layout_lots.source, layout_lots.replay)
    assert result["status"] == "pass", result
    assert result["mismatches"] == []
    assert result["files_compared"] == len(load_json(layout_lots.source / "manifest.json")["artifacts"]) + 1
    assert snapshot(layout_lots.source) == snapshot(layout_lots.replay)
    assert layout_lots.written_bytes < INTEGRATION_BUDGET


def test_compact_layout_pipeline_preserves_train_isolation_and_receipts(layout_lots):
    fixture = layout_lots.partitioned_bundle
    selected = set(fixture["plan"]["partitions"]["train"])
    all_texts = {a["id"]: a for a in fixture["catalog"]["assets"] if a["kind"] == "text"}
    assert len(selected) == 3 and len(all_texts) == 9
    for root in (layout_lots.source, layout_lots.replay):
        manifest = load_json(root / "manifest.json")
        config = load_json(root / "config.json")
        registry = load_json(root / "assets.json")
        page = load_json(root / manifest["pages"][0]["path"])
        assert {a["id"] for a in registry["assets"] if a["kind"] == "text"} == selected
        assert {s["asset_id"] for s in page["provenance"]["text_spans"]} <= selected
        assert page["provenance"]["parameters"]["partition"] == "train"
        receipt = manifest["extensions"]["mf:partition"]
        assert receipt["name"] == "train" and config["partition"] == receipt
        assert receipt["sha256"] == sha256(root / receipt["path"])
        assert receipt["source_catalog_sha256"] == sha256(root / receipt["source_catalog_path"])
        copied_catalog = load_json(root / receipt["source_catalog_path"])
        assert {a["id"] for a in copied_catalog["assets"] if a["kind"] == "text"} == set(all_texts)
        imported = manifest["extensions"]["mf:import_report"]
        assert imported["sha256"] == sha256(root / imported["path"])
        assert load_json(root / imported["path"])["external_protection"] == "NOT EVALUATED"
        for asset_id in set(all_texts) - selected:
            assert not (root / all_texts[asset_id]["path"]).exists()
