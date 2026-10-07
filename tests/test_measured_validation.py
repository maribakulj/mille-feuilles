"""Rehashed masks, diagnostic claims and resolved profiles remain auditable."""

import json

import numpy as np
from PIL import Image, ImageDraw
import pytest

from mille_feuilles.degrade import apply, degradation_seed, profile_sha256, sample_parameters
from mille_feuilles.diagnostics import document, ideal_mask, save_mask
from mille_feuilles.validation import MEASURED_PROFILE, validate_dataset, validate_page
from test_provenance_v3 import dataset as base_dataset, page as page  # noqa: F401
from test_provenance_v3 import digest, write_json

PROFILE = {
    "format": "mille-feuilles-degradation-profile", "version": "1", "name": "fixture",
    "description": "Tiny synthetic measurements, not calibrated", "calibrated": False,
    "oversampling": 1,
    "families": {
        "ink_loss": {"erosion": {"const": 0}, "break_density": {"const": 0},
                     "break_scale_px": {"const": 1}},
        "contrast": {"paper_level": {"const": 240}, "ink_level": {"const": 80}},
        "illumination": {"amplitude": {"const": 0}, "direction_degrees": {"const": 0}},
        "blur": {"sigma_px": {"const": 0}}, "noise": {"sigma": {"const": 0}},
    },
}
ORDER = {"readable": 0, "uncertain": 1, "illegible": 2}


def read(root, relative):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def edit(root, relative, mutate):
    value = read(root, relative)
    mutate(value)
    write_json(root / relative, value)


def reseal(root):
    """Refresh all hashes but never regenerate the diagnostics after a mutation."""
    manifest = read(root, "manifest.json")
    reference = manifest["extensions"]["mf:degradation_profile"]
    reference["sha256"] = digest(root / reference["path"])
    for record in manifest["pages"]:
        page = read(root, record["path"])
        page["image"]["sha256"] = digest(root / page["image"]["path"])
        if "mf:diagnostics" in page.get("extensions", {}):
            diagnostic = page["extensions"]["mf:diagnostics"]
            for path_field, hash_field in (("path", "sha256"), ("mask_path", "mask_sha256")):
                if (root / diagnostic[path_field]).is_file():
                    diagnostic[hash_field] = digest(root / diagnostic[path_field])
        write_json(root / record["path"], page)
        record["sha256"] = digest(root / record["path"])
    for ref in (manifest["config"], manifest["assets"]):
        ref["sha256"] = digest(root / ref["path"])
    manifest["artifacts"] = [
        {"path": path.relative_to(root).as_posix(), "sha256": digest(path), "role": "fixture"}
        for path in sorted(root.rglob("*")) if path.is_file() and path.name != "manifest.json"
    ]
    write_json(root / "manifest.json", manifest)


def set_labels(page, result):
    for word in page["words"]:
        word["legibility"] = result["words"][word["id"]]["legibility"]
    words = {word["id"]: word for word in page["words"]}
    for line in page["lines"]:
        line["legibility"] = max((words[wid]["legibility"] for wid in line["word_ids"]), key=ORDER.get)


@pytest.fixture
def measured(request):
    root = request.getfixturevalue("base_dataset")
    page = read(root, "pages/p1.json")
    page["profile"] = MEASURED_PROFILE
    params = sample_parameters(PROFILE, degradation_seed(1, 0))
    page["provenance"]["parameters"].update(
        degradation_profile=params, oversampling=1, raster_width=512, raster_height=512,
        legibility_method="heuristic-v1", angle_degrees=0.0,
        paper_level=240, ink_level=80, blur_radius=0,
    )
    canvas = Image.new("L", (512, 512), 0)
    drawing = ImageDraw.Draw(canvas)
    for word in page["words"]:
        left, top = word["polygon"][0]
        right, bottom = word["polygon"][2]
        drawing.rectangle((left + 2, top + 4, right - 2, bottom - 4), fill=255)
    coverage = np.asarray(canvas, dtype=np.float32) / 255
    pixels, page["transforms"] = apply(coverage, params)
    page["transforms"].insert(0, {
        "kind": "rotation", "geometry": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
        "parameters": {"degrees": 0.0, "resampling": "bicubic", "center": [256, 256], "fill": 0},
    })
    mask = ideal_mask(coverage)
    # Retain source geometry/text, while exercising all three measured labels.
    for index, word in enumerate(page["words"][:2]):
        left, top = word["polygon"][0]
        right, bottom = word["polygon"][2]
        for y in range(top, bottom + 1):
            if index == 0 or y % 2 == 0:
                pixels[y, left:right + 1] = 240
    Image.fromarray(pixels).save(root / "images/p1.png", dpi=(150, 150))
    page["image"]["sha256"] = digest(root / "images/p1.png")
    mask_sha = save_mask(mask, root / "qa/masks/p1.png")
    result = document(pixels, mask, page, image_sha256=page["image"]["sha256"], mask_sha256=mask_sha)
    set_labels(page, result)
    write_json(root / "qa/diagnostics/p1.json", result)
    page["extensions"] = {"mf:diagnostics": {
        "version": "1", "path": "qa/diagnostics/p1.json", "sha256": digest(root / "qa/diagnostics/p1.json"),
        "mask_path": "qa/masks/p1.png", "mask_sha256": mask_sha,
    }}
    write_json(root / "pages/p1.json", page)
    write_json(root / "provenance/degradation-profile.json", PROFILE)
    edit(root, "config.json", lambda config: config.update(render={"seed": 1, "degradation_profile": PROFILE}))
    edit(root, "manifest.json", lambda manifest: manifest.update(profile=MEASURED_PROFILE, extensions={
        "mf:degradation_profile": {"path": "provenance/degradation-profile.json",
                                    "sha256": digest(root / "provenance/degradation-profile.json")},
    }))
    reseal(root)
    return root


def errors(root):
    return validate_dataset(root, verify_exports=False)["errors"]


def test_measured_profile_accepts_recomputed_labels_and_exact_source_provenance(measured):
    page = read(measured, "pages/p1.json")
    assert {word["legibility"] for word in page["words"]} == {"readable", "uncertain", "illegible"}
    assert validate_page(page) == []
    assert errors(measured) == []
    assert digest(measured / "provenance/degradation-profile.json") != profile_sha256(PROFILE)


@pytest.mark.parametrize("field,mutate", [
    ("words", lambda diagnostics: diagnostics["words"]["w0"].update(retention=1.0)),
    ("thresholds", lambda diagnostics: diagnostics["thresholds"]["readable"].update(min_contrast=0)),
    ("inputs", lambda diagnostics: diagnostics["inputs"]["mask"].update(sha256="a" * 64)),
    ("words", lambda diagnostics: diagnostics["words"].pop("w0")),
    ("words", lambda diagnostics: diagnostics["words"].update(invented={"legibility": "readable"})),
])
def test_diagnostic_claims_are_recomputed_even_after_rehash(measured, field, mutate):
    edit(measured, "qa/diagnostics/p1.json", mutate)
    reseal(measured)
    actual = errors(measured)
    assert any("recomputed diagnostics" in error and field in error for error in actual), actual
    assert not any("SHA-256 mismatch" in error for error in actual)


def test_falsified_canonical_word_labels_cannot_override_measurements(measured):
    def mutate(page):
        for word in page["words"]:
            word["legibility"] = "readable"
        for line in page["lines"]:
            line["legibility"] = "readable"
    edit(measured, "pages/p1.json", mutate)
    reseal(measured)
    assert any("legibility differs from recomputed" in error for error in errors(measured))


def test_line_keeps_worst_word_label_under_measured_profile(measured):
    page = read(measured, "pages/p1.json")
    page["lines"][0]["legibility"] = "readable"
    assert any("worst word legibility" in error for error in validate_page(page))


@pytest.mark.parametrize("relative", ["qa/diagnostics/p1.json", "qa/masks/p1.png",
                                     "provenance/degradation-profile.json"])
def test_measured_files_require_artifact_entries(measured, relative):
    edit(measured, "manifest.json", lambda manifest: manifest.update(
        artifacts=[item for item in manifest["artifacts"] if item["path"] != relative]))
    assert any("inventory" in error for error in errors(measured))


@pytest.mark.parametrize("relative", ["qa/diagnostics/p1.json", "provenance/degradation-profile.json"])
def test_strict_json_rejects_rehashed_duplicate_keys(measured, relative):
    path = measured / relative
    content = path.read_text(encoding="utf-8")
    path.write_text('{"duplicate":1,"duplicate":2,' + content[1:], encoding="utf-8")
    reseal(measured)
    assert any("duplicate JSON key" in error for error in errors(measured))


@pytest.mark.parametrize("mode,size", [("L", (512, 512)), ("1", (256, 512))])
def test_rehashed_mask_requires_one_bit_and_final_dimensions(measured, mode, size):
    Image.new(mode, size, 0).save(measured / "qa/masks/p1.png")
    reseal(measured)
    assert any("PNG 1 bit" in error for error in errors(measured))


def test_rehashed_blank_mask_changes_diagnostics(measured):
    Image.new("1", (512, 512), 0).save(measured / "qa/masks/p1.png")
    reseal(measured)
    assert any("recomputed diagnostics" in error for error in errors(measured))


def test_rehashed_final_pixels_change_diagnostics(measured):
    Image.new("L", (512, 512), 240).save(measured / "images/p1.png", dpi=(150, 150))
    reseal(measured)
    assert any("recomputed diagnostics" in error for error in errors(measured))


@pytest.mark.parametrize("field,value", [("seed", 0), ("profile_sha256", "a" * 64),
                                         ("contrast", {"paper_level": 240, "ink_level": 90})])
def test_resolved_parameters_must_equal_seeded_profile(measured, field, value):
    edit(measured, "pages/p1.json", lambda page: page["provenance"]["parameters"]["degradation_profile"].update({field: value}))
    reseal(measured)
    assert any("resolved parameters differ" in error for error in errors(measured))


@pytest.mark.parametrize("mutate,fragment", [
    (lambda page: page["transforms"].reverse(), "family order"),
    (lambda page: page["transforms"][2]["parameters"].update(ink_level=90), "parameters disagree"),
    (lambda page: page["transforms"][1]["parameters"].update(broken_pixels=1), "broken_pixels"),
    (lambda page: page["transforms"].append({"kind": "untracked", "geometry": "identity", "parameters": {}}),
     "undeclared photometric"),
])
def test_photometric_transforms_match_resolved_profile(measured, mutate, fragment):
    edit(measured, "pages/p1.json", mutate)
    reseal(measured)
    assert any(fragment in error for error in errors(measured))


@pytest.mark.parametrize("mutate", [
    lambda profile: profile.update(calibrated=True),
    lambda profile: profile["families"]["noise"].update(sigma={"const": 31}),
])
def test_rehashed_profile_must_be_uncalibrated_and_bounded(measured, mutate):
    edit(measured, "provenance/degradation-profile.json", mutate)
    edited = read(measured, "provenance/degradation-profile.json")
    edit(measured, "config.json", lambda config: config["render"].update(degradation_profile=edited))
    reseal(measured)
    assert any("invalid degradation profile" in error for error in errors(measured))


def test_config_profile_must_equal_embedded_profile(measured):
    edit(measured, "config.json", lambda config: config["render"]["degradation_profile"].update(name="other"))
    reseal(measured)
    assert any("differs from config.render" in error for error in errors(measured))


def test_measured_receipt_is_mandatory(measured):
    page = read(measured, "pages/p1.json")
    del page["extensions"]["mf:diagnostics"]
    assert any("mf:diagnostics" in error for error in validate_page(page))


def test_mask_path_is_bound_to_page_identity_before_reading(measured):
    edit(measured, "pages/p1.json", lambda page: page["extensions"]["mf:diagnostics"].update(mask_path="qa/masks/other.png"))
    reseal(measured)
    assert any("mask path does not match page identity" in error for error in errors(measured))


def test_external_mask_symlink_is_rejected(measured, tmp_path):
    path = measured / "qa/masks/p1.png"
    outside = tmp_path.parent / f"outside-mask-{tmp_path.name}.png"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    assert any("escapes dataset root" in error for error in errors(measured))


def test_legacy_profile_still_rejects_nonreadable_supervision(measured):
    page = read(measured, "pages/p1.json")
    page["profile"] = "fr_press_19c_columns_4_6"
    del page["extensions"]["mf:diagnostics"]
    del page["provenance"]["parameters"]["degradation_profile"]
    write_json(measured / "pages/p1.json", page)
    edit(measured, "config.json", lambda config: config["render"].pop("degradation_profile"))
    reseal(measured)
    edit(measured, "manifest.json", lambda manifest: (
        manifest.update(profile="fr_press_19c_columns_4_6"), manifest.pop("extensions")))
    assert any("excludes uncertain/illegible" in error for error in errors(measured))


@pytest.mark.parametrize("field,value", [("oversampling", 2), ("raster_width", 1024),
                                         ("legibility_method", "unmeasured")])
def test_raster_metadata_agrees_with_profile_and_final_image(measured, field, value):
    edit(measured, "pages/p1.json", lambda page: page["provenance"]["parameters"].update({field: value}))
    reseal(measured)
    assert any(f"measured parameter {field}" in error for error in errors(measured))


def configure_double_sampling(measured):
    profile = read(measured, "provenance/degradation-profile.json")
    profile["oversampling"] = 2
    write_json(measured / "provenance/degradation-profile.json", profile)
    edit(measured, "config.json", lambda config: config["render"].update(degradation_profile=profile))
    page = read(measured, "pages/p1.json")
    page["provenance"]["parameters"].update(
        oversampling=2, raster_width=1024, raster_height=1024,
        degradation_profile=sample_parameters(profile, degradation_seed(1, 0)),
    )
    scales = [{
        "kind": "mf:oversampling", "geometry": {"matrix": [[2, 0, 0], [0, 2, 0], [0, 0, 1]]},
        "parameters": {"factor": 2, "source_size": [512, 512], "target_size": [1024, 1024]},
    }, {
        "kind": "mf:downsample", "geometry": {"matrix": [[0.5, 0, 0], [0, 0.5, 0], [0, 0, 1]]},
        "parameters": {"factor": 2, "resampling": "box-mean", "source_size": [1024, 1024],
                       "target_size": [512, 512]},
    }]
    page["transforms"][0]["parameters"]["center"] = [512, 512]
    page["transforms"] = [scales[0], page["transforms"][0], scales[1]] + page["transforms"][1:]
    write_json(measured / "pages/p1.json", page)
    reseal(measured)


def test_double_sampling_declares_exact_scale_and_reduction_before_photometry(measured):
    configure_double_sampling(measured)
    assert errors(measured) == []
    edit(measured, "pages/p1.json", lambda page: page["transforms"][2]["parameters"].update(resampling="nearest"))
    reseal(measured)
    assert any("downsample transforms disagree" in error for error in errors(measured))


@pytest.mark.parametrize("mutate", [
    lambda page: page["transforms"][0]["geometry"]["matrix"][0].__setitem__(2, 1),
    lambda page: page["transforms"][0]["parameters"].update(center=[0, 0]),
    lambda page: page["transforms"][0]["parameters"].update(fill=255),
    lambda page: page["transforms"][0]["parameters"].update(degrees=0.1),
    lambda page: page["transforms"][0]["parameters"].update(resampling="nearest"),
    lambda page: page["transforms"][0].update(kind="arbitrary-affine"),
    lambda page: page["transforms"].pop(0),
    lambda page: page["transforms"].insert(0, dict(page["transforms"][0])),
    lambda page: page["provenance"]["parameters"].update(angle_degrees=0.2),
])
def test_rotation_metadata_and_exact_geometric_sequence_are_not_forgeable(measured, mutate):
    edit(measured, "pages/p1.json", mutate)
    reseal(measured)
    actual = errors(measured)
    assert any("geometry sequence/matrix" in error for error in actual), actual
    assert not any("SHA-256 mismatch" in error for error in actual)


@pytest.mark.parametrize("angle", [True, None, -0.3501, 0.3501])
def test_measured_angle_is_a_number_within_declared_limits(measured, angle):
    edit(measured, "pages/p1.json", lambda page: page["provenance"]["parameters"].update(angle_degrees=angle))
    reseal(measured)
    assert any("angle_degrees must be finite" in error for error in errors(measured))


@pytest.mark.parametrize("field,value", [("paper_level", 239), ("ink_level", 81), ("blur_radius", 0.1)])
def test_duplicate_photometric_metadata_must_match_resolved_profile(measured, field, value):
    edit(measured, "pages/p1.json", lambda page: page["provenance"]["parameters"].update({field: value}))
    reseal(measured)
    assert any(f"measured parameter {field} differs" in error for error in errors(measured))


def test_broken_pixel_count_is_bounded_by_final_not_supersampled_image(measured):
    configure_double_sampling(measured)
    profile = read(measured, "provenance/degradation-profile.json")
    profile["families"]["ink_loss"]["break_density"] = {"const": 0.1}
    write_json(measured / "provenance/degradation-profile.json", profile)
    edit(measured, "config.json", lambda config: config["render"].update(degradation_profile=profile))
    page = read(measured, "pages/p1.json")
    page["provenance"]["parameters"]["degradation_profile"] = sample_parameters(profile, degradation_seed(1, 0))
    ink_loss = next(transform for transform in page["transforms"] if transform["kind"] == "mf:degrade:ink_loss")
    ink_loss["parameters"].update(break_density=0.1, broken_pixels=512 * 512 + 1)
    write_json(measured / "pages/p1.json", page)
    reseal(measured)
    assert any("broken_pixels is invalid" in error for error in errors(measured))


def test_all_ink_mask_is_rejected_even_with_recomputed_diagnostics_and_labels(measured):
    page = read(measured, "pages/p1.json")
    mask = np.ones((512, 512), dtype=bool)
    mask_sha = save_mask(mask, measured / "qa/masks/p1.png")
    with Image.open(measured / "images/p1.png") as image:
        pixels = np.asarray(image).copy()
    result = document(pixels, mask, page, image_sha256=page["image"]["sha256"], mask_sha256=mask_sha)
    set_labels(page, result)
    write_json(measured / "pages/p1.json", page)
    write_json(measured / "qa/diagnostics/p1.json", result)
    reseal(measured)
    assert validate_page(read(measured, "pages/p1.json")) == []
    actual = errors(measured)
    assert any("outside all block polygons" in error for error in actual), actual
    assert not any("SHA-256 mismatch" in error for error in actual)


def test_ideal_mask_support_includes_nontextual_rules(measured):
    page = read(measured, "pages/p1.json")
    page["blocks"].append({
        "id": "rule", "category": "separateur", "article_id": None, "line_ids": [],
        "polygon": [[300, 250], [310, 250], [310, 252], [300, 252]],
    })
    page["reading_order"]["unordered_block_ids"].append("rule")
    with Image.open(measured / "qa/masks/p1.png") as image:
        mask = np.asarray(image, dtype=bool).copy()
    with Image.open(measured / "images/p1.png") as image:
        pixels = np.asarray(image).copy()
    mask[250:252, 300:310] = True
    pixels[250:252, 300:310] = 80
    Image.fromarray(pixels).save(measured / "images/p1.png", dpi=(150, 150))
    mask_sha = save_mask(mask, measured / "qa/masks/p1.png")
    image_sha = digest(measured / "images/p1.png")
    result = document(pixels, mask, page, image_sha256=image_sha, mask_sha256=mask_sha)
    set_labels(page, result)
    write_json(measured / "pages/p1.json", page)
    write_json(measured / "qa/diagnostics/p1.json", result)
    reseal(measured)
    assert errors(measured) == []
