"""Small synthetic rasters: frozen legacy output and measured-profile geometry."""

from copy import deepcopy
import hashlib
import json
import shutil

import numpy as np
from PIL import Image, ImageDraw
import pytest

from mille_feuilles import degrade, diagnostics
from mille_feuilles.exports import export_coco, export_page, validate_exports
from mille_feuilles.io import sha256
from mille_feuilles.pipeline import prepare_assets
from mille_feuilles.render import Composer, Config, PROFILE_MEASURED, render_page
from mille_feuilles.validation import validate_page


# Captured before introducing measured rendering, using the locked environment
# and bundled original synthetic sources at commit 7fa4b2e (schema 0.3.0).
LEGACY = {
    "clean": ("5e2adefcd2936484108f824e70fce45aa6f1dc31e2773c34bb1f32db23208949",
              "45c35aa09733d4f44d8618f939eba63f95f103fee870a76ccbd9adea3362673e"),
    "aged": ("9eaa24cc11e04697539d34cf893446c386b6dbd24ef4724ba6b78ee09d8e299a",
             "d11fba40cfc25049f71f3210cd66b4ad4b9457321e1260cea441a4cb12977ad7"),
    "faint": ("89b53a6c072fa3ea54d28d13321267f04fd93bc8dff13e167e2c3f907103ca23",
              "70b7ab3380c1a9e715221270623b5a2de2c5d18d91aba8075bc1580473f96154"),
    "mixed": ("c416cd8f1a40c12dec978dc8f3a4f2b6ab2cb96dd5db01d79cd8d1954df37093",
              "1e1d275edfe0dad08a642bc7e733115238019a99ef6ad11fd648d4b1e3d5ff5b"),
}


@pytest.fixture(scope="module")
def asset_fixture(tmp_path_factory):
    root = tmp_path_factory.mktemp("measured_render")
    source = root / "source"
    source.mkdir()
    return root, source, prepare_assets(source)


def render_fixture(fixture, name, profile=None, mode="mixed", seed=731):
    parent, source, assets = fixture
    root = parent / name
    shutil.copytree(source / "assets", root / "assets")
    config = Config(width=800, height=1100, columns=4, degradation=mode, seed=seed,
                    degradation_profile=profile)
    return root, config, render_page(config, 0, assets, root)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def geometry_and_sources(page):
    result = {key: deepcopy(page[key]) for key in (
        "articles", "blocks", "lines", "words", "reading_order"
    )}
    for obj in result["lines"] + result["words"]:
        obj.pop("legibility")
    result["spans"] = page["provenance"]["text_spans"]
    return result


@pytest.fixture(scope="module")
def measured_pages(asset_fixture):
    return {
        name: render_fixture(asset_fixture, name, degrade.load_profile(name))
        for name in ("identity", "controlled-v1")
    }


@pytest.mark.parametrize("mode", LEGACY)
def test_legacy_png_and_canonical_json_remain_byte_identical(asset_fixture, mode):
    root, config, page = render_fixture(asset_fixture, f"legacy-{mode}", mode=mode)
    encoded = (json.dumps(page, ensure_ascii=False, sort_keys=True, indent=2,
                          allow_nan=False) + "\n").encode()
    assert (page["image"]["sha256"], hashlib.sha256(encoded).hexdigest()) == LEGACY[mode]
    assert "degradation_profile" not in config.as_dict()
    assert "degradation_profile" not in page["provenance"]["parameters"]
    assert not (root / "qa/masks").exists()
    assert not (root / "qa/diagnostics").exists()


def test_profile_families_do_not_change_native_composition_or_ideal_mask(measured_pages):
    root, _, identity = measured_pages["identity"]
    other, _, controlled = measured_pages["controlled-v1"]
    assert geometry_and_sources(identity) == geometry_and_sources(controlled)
    assert identity["transforms"][0] == controlled["transforms"][0]
    relative = diagnostics.mask_path(identity["page_id"])
    assert (root / relative).read_bytes() == (other / relative).read_bytes()
    assert identity["image"]["sha256"] != controlled["image"]["sha256"]


@pytest.mark.parametrize("name", ["identity", "controlled-v1"])
def test_measured_sidecars_and_labels_recompute_exactly(measured_pages, name):
    root, config, page = measured_pages[name]
    assert page["profile"] == PROFILE_MEASURED
    assert validate_page(page) == []
    extension = page["extensions"]["mf:diagnostics"]
    assert extension == {
        "version": "1", "path": diagnostics.diagnostics_path(page["page_id"]),
        "sha256": sha256(root / diagnostics.diagnostics_path(page["page_id"])),
        "mask_path": diagnostics.mask_path(page["page_id"]),
        "mask_sha256": sha256(root / diagnostics.mask_path(page["page_id"])),
    }
    image = np.asarray(Image.open(root / page["image"]["path"]), dtype=np.uint8)
    mask = diagnostics.load_mask(root / extension["mask_path"], image.shape)
    stored = read(root / extension["path"])
    assert stored == diagnostics.document(
        image, mask, page, image_sha256=sha256(root / page["image"]["path"]),
        mask_sha256=extension["mask_sha256"],
    )
    assert page["provenance"]["parameters"]["degradation_profile"] == degrade.sample_parameters(
        config.degradation_profile, degrade.degradation_seed(config.seed, 0)
    )
    labels = {word["id"]: word["legibility"] for word in page["words"]}
    assert labels == {wid: value["legibility"] for wid, value in stored["words"].items()}
    ranks = {"readable": 0, "uncertain": 1, "illegible": 2}
    for line in page["lines"]:
        assert line["legibility"] == max((labels[wid] for wid in line["word_ids"]), key=ranks.get)


def test_measured_mode_does_not_use_legacy_degradation_draws(asset_fixture, measured_pages):
    _, _, reference = measured_pages["identity"]
    _, _, page = render_fixture(asset_fixture, "identity-clean-argument",
                                degrade.load_profile("identity"), mode="clean")
    assert page == reference


def test_lost_ink_keeps_ideal_mask_and_changes_measured_labels(asset_fixture, measured_pages):
    profile = degrade.load_profile("identity")
    profile["name"] = "destructive-fixture"
    profile["families"] = {"ink_loss": {
        "erosion": {"const": 1}, "break_density": {"const": 0.5},
        "break_scale_px": {"const": 0.5},
    }}
    root, _, page = render_fixture(asset_fixture, "destructive", profile)
    original_root, _, original = measured_pages["identity"]
    assert geometry_and_sources(page) == geometry_and_sources(original)
    relative = diagnostics.mask_path(page["page_id"])
    assert (root / relative).read_bytes() == (original_root / relative).read_bytes()
    report = read(root / diagnostics.diagnostics_path(page["page_id"]))
    assert report["page"]["ink_loss_fraction"] > 0.5
    assert any(word["legibility"] == "illegible" for word in page["words"])
    assert any(word["contrast"] == 0 for word in report["words"].values())


def test_measured_cover_uses_white_text_and_200_level_rules(asset_fixture):
    _, source, assets = asset_fixture
    composer = Composer(Config(width=800, height=1100, columns=4,
                               degradation_profile=degrade.load_profile("identity")),
                        0, assets, source)
    composer.separator(20, 20, 100, 22)
    image = np.asarray(composer.canvas)
    assert image[21, 50] == 200
    assert image[0, 0] == 0
    assert composer.ink == 255


@pytest.fixture(scope="module")
def oversampled_pages(asset_fixture):
    result = {}
    for name in ("identity", "controlled-v1"):
        profile = degrade.load_profile(name)
        profile["oversampling"] = 2
        result[name] = render_fixture(asset_fixture, f"oversampled-{name}", profile)
    return result


def test_oversampling_is_validated_in_the_profile():
    profile = degrade.load_profile("identity")
    profile["oversampling"] = 3
    with pytest.raises(ValueError, match="oversampling"):
        Config(degradation_profile=profile).validate()


def test_oversampled_profiles_keep_geometry_and_mask_identical(oversampled_pages):
    root, _, identity = oversampled_pages["identity"]
    other, _, controlled = oversampled_pages["controlled-v1"]
    assert geometry_and_sources(identity) == geometry_and_sources(controlled)
    assert identity["transforms"][:3] == controlled["transforms"][:3]
    relative = diagnostics.mask_path(identity["page_id"])
    assert (root / relative).read_bytes() == (other / relative).read_bytes()
    assert identity["image"]["sha256"] != controlled["image"]["sha256"]
    for page in (identity, controlled):
        assert validate_page(page) == []
        assert page["image"]["width"] == 800 and page["image"]["height"] == 1100
        params = page["provenance"]["parameters"]
        assert (params["raster_width"], params["raster_height"], params["oversampling"]) == (1600, 2200, 2)
        matrix = np.eye(3)
        for transform in page["transforms"]:
            if transform["geometry"] != "identity":
                matrix = np.asarray(transform["geometry"]["matrix"]) @ matrix
        assert np.linalg.svd(matrix[:2, :2], compute_uv=False) == pytest.approx([1, 1])
        assert matrix @ [400, 550, 1] == pytest.approx([400, 550, 1])


def test_oversampled_geometry_and_measured_labels_survive_all_exports(oversampled_pages):
    root, _, page = oversampled_pages["controlled-v1"]
    assert any(word["legibility"] != "readable" for word in page["words"])
    export_page(page, root)
    export_coco([page], root)
    assert validate_exports(root, [page]) == []


def test_oversampling_retains_native_composition_positions_and_line_wraps(asset_fixture, monkeypatch):
    _, source, assets = asset_fixture
    original = Composer.add_line
    positions = []

    def capture(self, tokens, block, x, baseline, font, width, justify=False):
        positions.append((deepcopy(tokens), block["id"], x, baseline, font.size, width, justify))
        return original(self, tokens, block, x, baseline, font, width, justify)

    monkeypatch.setattr(Composer, "add_line", capture)
    recordings = []
    for factor in (1, 2):
        profile = degrade.load_profile("identity")
        profile["oversampling"] = factor
        composer = Composer(Config(width=800, height=1100, columns=4, seed=731,
                                   degradation_profile=profile), 0, assets, source)
        positions.clear()
        composer.content()
        recordings.append(deepcopy(positions))
    assert recordings[0] == recordings[1]


def test_oversampled_glyph_support_is_covered_before_geometry(asset_fixture):
    _, source, assets = asset_fixture
    profile = degrade.load_profile("identity")
    profile["oversampling"] = 2
    composer = Composer(Config(width=800, height=1100, columns=4, seed=731,
                               degradation_profile=profile), 0, assets, source)
    composer.content()
    envelope = Image.new("1", composer.canvas.size)
    draw = ImageDraw.Draw(envelope)
    objects = composer.words + [b for b in composer.blocks if not b["line_ids"]]
    for obj in objects:
        points = np.asarray(obj["polygon"]) * 2
        left, top = np.floor(points.min(axis=0))
        right, bottom = np.ceil(points.max(axis=0))
        draw.rectangle((left, top, right, bottom), fill=1)
    escaped = (np.asarray(composer.canvas) > 0) & ~np.asarray(envelope, dtype=bool)
    assert not escaped.any(), f"{escaped.sum()} oversampled ink pixels escape their annotations"


def test_mask_and_photometry_receive_reduced_grey_coverage(asset_fixture, monkeypatch):
    _, _, assets = asset_fixture
    profile = degrade.load_profile("identity")
    profile["oversampling"] = 2
    seen = {}
    apply = degrade.apply

    def capture(coverage, params):
        seen["coverage"] = coverage.copy()
        return apply(coverage, params)

    monkeypatch.setattr(degrade, "apply", capture)
    root, config, page = render_fixture(asset_fixture, "oversampled-coverage-order", profile)
    composer = Composer(config, 0, assets, root)
    composer.content()
    angle = composer.rng.uniform(-0.35, 0.35)
    rotated = composer.canvas.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=0)
    raster = np.asarray(rotated, dtype=np.float32) / np.float32(255)
    expected = raster.reshape(1100, 2, 800, 2).astype(np.float64).mean(axis=(1, 3)).astype(np.float32)
    assert np.array_equal(seen["coverage"], expected)
    mask = diagnostics.load_mask(root / diagnostics.mask_path(page["page_id"]), expected.shape)
    assert np.array_equal(mask, expected >= 0.5)
    reduced_boolean = (raster >= 0.5).reshape(1100, 2, 800, 2).mean(axis=(1, 3)) >= 0.5
    assert np.any(mask != reduced_boolean), "Fixture must distinguish grey reduction from mask reduction"
