"""Pixel-audit checks independent of declared readability or valid hashes."""

import importlib.util
import json
import shutil

import numpy as np
from PIL import Image
import pytest

from mille_feuilles.io import ROOT, sha256
from mille_feuilles.pipeline import build_dataset
from mille_feuilles.render import Config
from mille_feuilles.validation import load_json

spec = importlib.util.spec_from_file_location("audit_legibility", ROOT / "tools/audit_legibility.py")
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)
THRESHOLDS = audit_module.THRESHOLDS
audit_legibility = audit_module.audit_legibility
main = audit_module.main
measure_word = audit_module.measure_word


@pytest.fixture(scope="module")
def small_lot(tmp_path_factory):
    root = tmp_path_factory.mktemp("legibility") / "lot"
    report = build_dataset(
        root, Config(width=800, height=1100, columns=4, degradation="clean", seed=813), count=1
    )
    assert report["status"] == "pass", report["errors"]
    return root


def snapshot(root):
    return {str(path.relative_to(root)): sha256(path) for path in root.rglob("*") if path.is_file()}


def rehash(root, relative):
    digest = sha256(root / relative)
    manifest = load_json(root / "manifest.json")
    for entry in manifest["artifacts"] + manifest["pages"]:
        if entry["path"] == relative:
            entry["sha256"] = digest
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_all_words_are_measured_and_native_samples_leave_lot_unchanged(small_lot, tmp_path):
    before = snapshot(small_lot)
    report_path = tmp_path / "audit.json"
    samples_dir = tmp_path / "samples"
    report = audit_legibility(small_lot, report_path, samples_dir, max_samples=12)
    assert report["status"] == "pass", report["suspects"][:5] + report["errors"]
    manifest = load_json(small_lot / "manifest.json")
    page = load_json(small_lot / manifest["pages"][0]["path"])
    assert (
        report["summary"]["words_measured"]
        == report["summary"]["words_declared"]
        == len(page["words"])
    )
    assert report["summary"]["minimum_contrast_gray_levels"] >= 40
    assert report["summary"]["minimum_ink_pixels"] >= 2
    assert report["summary"]["minimum_effective_font_size_px"] >= 10
    assert report["thresholds"] == THRESHOLDS
    assert 1 <= len(report["samples"]) <= 12
    assert any(sample["punctuation_only"] for sample in report["samples"])
    assert any(sample["hyphenation_part"] == "start" for sample in report["samples"])
    assert any(sample["hyphenation_part"] == "end" for sample in report["samples"])
    assert report["sample_sheets"]
    assert snapshot(small_lot) == before
    assert load_json(report_path)["status"] == "pass"

    # Independently compare the displayed pixels against the original final PNG.
    # The tool may enlarge x2 nearest but must not resample or fabricate them.
    first_sheet = report["sample_sheets"][0]
    first_card = first_sheet["cards"][0]
    sample = next(s for s in report["samples"] if s["word_id"] == first_card["word_id"])
    assert sample["display_tile_count"] == 1
    with Image.open(small_lot / sample["image_path"]) as image:
        expected = image.convert("RGB").crop(sample["crop_box"])
    scale = sample["display_scale"]
    if scale == 2:
        expected = expected.resize(
            (expected.width * 2, expected.height * 2), Image.Resampling.NEAREST
        )
    with Image.open(first_sheet["path"]) as sheet:
        actual = sheet.crop((12, 94, 12 + expected.width, 94 + expected.height))
    assert np.array_equal(np.asarray(actual), np.asarray(expected))


def test_blank_rehashed_png_fails_on_every_word(small_lot, tmp_path):
    root = tmp_path / "blank"
    shutil.copytree(small_lot, root)
    manifest = load_json(root / "manifest.json")
    page_relative = manifest["pages"][0]["path"]
    page = load_json(root / page_relative)
    image = page["image"]
    Image.new("L", (image["width"], image["height"]), 255).save(root / image["path"])
    page["image"]["sha256"] = sha256(root / image["path"])
    (root / page_relative).write_text(json.dumps(page), encoding="utf-8")
    rehash(root, image["path"])
    rehash(root, page_relative)
    report = audit_legibility(root, tmp_path / "blank-audit.json")
    assert report["status"] == "fail"
    assert not report["errors"], "All hashes were updated; failure must come from actual pixels"
    assert report["summary"]["suspect_words"] == len(page["words"])
    assert report["summary"]["minimum_contrast_gray_levels"] == 0
    assert report["summary"]["minimum_ink_pixels"] == 0
    assert all("fewer_than_2_ink_pixels" in word["reasons"] for word in report["suspects"])


def test_legacy_version_measures_the_same_pixels_with_the_same_thresholds(small_lot, tmp_path):
    root = tmp_path / "legacy"
    shutil.copytree(small_lot, root)
    manifest = load_json(root / "manifest.json")
    assert manifest["schema_version"] == "0.3.0"
    manifest["schema_version"] = "0.2.0"
    for reference in manifest["pages"]:
        page = load_json(root / reference["path"])
        page["schema_version"] = "0.2.0"
        reference["source_group_ids"] = sorted({
            span["source_document_id"] for span in page["provenance"]["text_spans"]
        })
        for span in page["provenance"]["text_spans"]:
            del span["article_id"], span["block_ids"]
        (root / reference["path"]).write_text(json.dumps(page), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for reference in manifest["pages"]:
        rehash(root, reference["path"])
    current = audit_legibility(small_lot, tmp_path / "current.json", max_samples=0)
    legacy = audit_legibility(root, tmp_path / "legacy.json", max_samples=0)
    assert current["status"] == legacy["status"] == "pass"
    assert current["summary"] == legacy["summary"]
    assert current["thresholds"] == legacy["thresholds"] == THRESHOLDS


@pytest.mark.parametrize("version", ["0.1.0", "0.4.0"])
def test_unsupported_manifest_version_is_rejected(tmp_path, version):
    root = tmp_path / "unsupported"
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps({
        "schema_version": version, "dataset_id": "unsupported", "pages": [],
    }), encoding="utf-8")
    report = audit_legibility(root, tmp_path / "unsupported.json")
    assert report["status"] == "fail"
    assert report["summary"]["words_measured"] == 0
    assert any("Expected a version 0.2.0 or 0.3.0" in error for error in report["errors"])


@pytest.mark.parametrize("version", ["0.2.0", "0.4.0"])
def test_page_version_must_match_manifest_even_after_rehash(small_lot, tmp_path, version):
    root = tmp_path / "mixed-version"
    shutil.copytree(small_lot, root)
    manifest = load_json(root / "manifest.json")
    relative = manifest["pages"][0]["path"]
    page = load_json(root / relative)
    page["schema_version"] = version
    (root / relative).write_text(json.dumps(page), encoding="utf-8")
    rehash(root, relative)
    report = audit_legibility(root, tmp_path / "mixed-version.json")
    assert report["status"] == "fail"
    assert report["summary"]["words_measured"] == 0
    assert any("page schema_version differs" in error for error in report["errors"])
    assert not any("SHA-256 mismatch" in error for error in report["errors"])


def test_dark_pixels_outside_final_word_polygon_do_not_count_as_ink():
    pixels = np.full((40, 40), 255, dtype=np.uint8)
    pixels[8:11, 8:11] = 0  # Inside the bounding box, outside the diamond.
    word = {"polygon": [[20, 8], [32, 20], [20, 32], [8, 20]]}
    metric = measure_word(pixels, word, font_size=12, scale=1)
    assert metric["ink_pixels"] == 0
    assert "fewer_than_2_ink_pixels" in metric["reasons"]


def test_two_pixel_punctuation_can_pass_without_box_percentile_bias():
    pixels = np.full((40, 40), 240, dtype=np.uint8)
    pixels[20, 19:21] = 180
    word = {"polygon": [[10, 10], [30, 10], [30, 30], [10, 30]]}
    metric = measure_word(pixels, word, font_size=10, scale=1)
    assert metric["contrast_gray_levels"] == 60
    assert metric["ink_pixels"] == 2
    assert metric["reasons"] == []


@pytest.mark.parametrize(
    "gray,font_size,scale,reason",
    [
        (205, 12, 1, "contrast_below_40"),
        (30, 9, 1, "effective_font_size_below_10_px"),
        (30, 12, 0.5, "effective_font_size_below_10_px"),
        (30, None, 1, "font_size_missing"),
    ],
)
def test_fixed_contrast_and_effective_font_thresholds(gray, font_size, scale, reason):
    pixels = np.full((40, 40), 240, dtype=np.uint8)
    pixels[15:22, 15:22] = gray
    word = {"polygon": [[10, 10], [30, 10], [30, 30], [10, 30]]}
    assert reason in measure_word(pixels, word, font_size, scale)["reasons"]


def test_cli_returns_nonzero_for_unauditable_input(tmp_path, capsys):
    root = tmp_path / "broken"
    root.mkdir()
    (root / "manifest.json").write_text('{"dataset_id":"a","dataset_id":"b"}')
    status = main([str(root), "--report", str(tmp_path / "failure.json")])
    assert status == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "fail"
    assert any("duplicate JSON key" in error for error in report["errors"])


@pytest.mark.parametrize("destination", ["report", "samples"])
def test_outputs_inside_dataset_are_rejected_without_changes(small_lot, tmp_path, destination):
    before = snapshot(small_lot)
    report = (
        small_lot / "forbidden-audit.json" if destination == "report" else tmp_path / "audit.json"
    )
    samples = small_lot / "forbidden-samples" if destination == "samples" else None
    with pytest.raises(ValueError, match="outside the dataset"):
        audit_legibility(small_lot, report, samples)
    assert snapshot(small_lot) == before


def test_existing_report_is_never_overwritten(small_lot, tmp_path):
    report = tmp_path / "my-notes.json"
    report.write_text("keep my notes")
    with pytest.raises(ValueError, match="already exists"):
        audit_legibility(small_lot, report)
    assert report.read_text() == "keep my notes"


def test_samples_directory_must_be_new(small_lot, tmp_path):
    samples = tmp_path / "existing-samples"
    samples.mkdir()
    witness = samples / "my-note.txt"
    witness.write_text("keep this")
    with pytest.raises(ValueError, match="already exists"):
        audit_legibility(small_lot, tmp_path / "audit.json", samples)
    assert list(samples.iterdir()) == [witness]
    assert witness.read_text() == "keep this"


def test_sample_budget_above_150_is_refused(small_lot, tmp_path):
    with pytest.raises(ValueError, match="between 0 and 150"):
        audit_legibility(small_lot, tmp_path / "audit.json", max_samples=151)
