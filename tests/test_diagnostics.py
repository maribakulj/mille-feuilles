"""Page and word diagnostics against the ideal mask; heuristic legibility labels."""

import json
from copy import deepcopy

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from mille_feuilles.degrade import apply, load_profile, sample_parameters
from mille_feuilles.diagnostics import (
    LEGIBILITY_THRESHOLDS,
    compare,
    ideal_mask,
    label_legibility,
    load_mask,
    measure,
    otsu_threshold,
    reference_levels,
    save_mask,
)
from mille_feuilles.io import ROOT

# Small ideal coverages with exact word polygons, shared with test_degrade.
FONT = ROOT / "assets/fonts/oldstandardtt/OldStandard-Regular.ttf"
LINES = [
    "Le conseil municipal a voté le budget",
    "du canal, après une séance animée.",
    "Foire aux chevaux : dimanche, place du marché.",
]


def coverage_page(size=22, width=520, height=150, rule=True, contrast=None):
    """Return (coverage float32, page dict). Words are boxes from the font metrics."""
    font = ImageFont.truetype(str(FONT), size=size, layout_engine=ImageFont.Layout.BASIC)
    canvas = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(canvas)
    ascent, descent = font.getmetrics()
    words, y = [], 10 + ascent
    for line in LINES:
        x = 12.0
        for text in line.split():
            advance = font.getlength(text)
            draw.text((x, y), text, fill=255, font=font, anchor="ls")
            words.append({
                "id": f"w{len(words):03d}",
                "text": text,
                "polygon": [[x, y - ascent], [x + advance, y - ascent], [x + advance, y + descent], [x, y + descent]],
            })
            x += advance + font.getlength(" ")
        y += ascent + descent + 6
    if rule:
        draw.rectangle((10, height - 8, width - 10, height - 6), fill=200)  # separator at 200/255
    coverage = np.asarray(canvas, dtype=np.float32) / 255.0
    parameters = {}
    if contrast is not None:
        parameters["degradation_profile"] = {
            "profile": "fixture", "profile_sha256": "0" * 64, "seed": 0, "contrast": contrast,
        }
    page = {"page_id": "fixture", "words": words, "provenance": {"parameters": parameters}}
    return coverage, page


def identity_image(coverage):
    image, _ = apply(coverage, sample_parameters(load_profile("identity"), 0))
    return image


def test_identity_page_is_ideal_and_every_word_readable():
    coverage, page = coverage_page()
    result = measure(identity_image(coverage), ideal_mask(coverage), page)
    assert result["format"] == "mille-feuilles-diagnostics" and result["legibility_method"] == "heuristic-v1"
    assert result["page"]["ink_loss_fraction"] == 0.0
    assert result["page"]["noise_mad_sigma"] == 0.0
    # Antialiased glyph edges with coverage >= 0.5 belong to the mask: ink median > 0.
    assert result["page"]["paper_median"] == 255.0 and 0.0 <= result["page"]["ink_median"] < 128.0
    assert result["page"]["legibility"] == {"readable": len(page["words"]), "uncertain": 0, "illegible": 0}
    assert result["references"] == {"paper_level": 255.0, "ink_level": 0.0}


def test_reference_ink_comes_from_resolved_contrast_with_defaults():
    _, page = coverage_page()
    assert reference_levels(page) == (255.0, 0.0)
    _, page = coverage_page()
    page["provenance"]["parameters"]["degradation_profile"] = sample_parameters(load_profile("identity"), 0)
    assert reference_levels(page) == (255.0, 0.0)
    params = sample_parameters(load_profile("controlled-v1"), 0)
    page["provenance"]["parameters"]["degradation_profile"] = params
    assert reference_levels(page) == (params["contrast"]["paper_level"], params["contrast"]["ink_level"])


@pytest.mark.parametrize("value", [float("nan"), 10**400, 300])
def test_hostile_page_parameters_are_refused_before_measuring(value):
    from mille_feuilles.degrade import ProfileError

    coverage, page = coverage_page()
    params = sample_parameters(load_profile("controlled-v1"), 0)
    params["contrast"]["ink_level"] = value
    page["provenance"]["parameters"]["degradation_profile"] = params
    with pytest.raises(ProfileError):
        measure(identity_image(coverage), ideal_mask(coverage), page)


def _word_region(word):
    xs = [int(p[0]) for p in word["polygon"]]
    ys = [int(p[1]) for p in word["polygon"]]
    return slice(min(ys), max(ys) + 1), slice(min(xs), max(xs) + 1)


def test_erased_word_is_illegible_half_erased_uncertain_pale_illegible():
    coverage, page = coverage_page()
    mask = ideal_mask(coverage)
    image = identity_image(coverage).astype(np.int16)
    erased, half, pale = page["words"][2], page["words"][4], page["words"][5]
    region = _word_region(erased)
    image[region] = np.where(mask[region], 255, image[region])
    # Every other row of ink removed: retention ~ 0.5 with full contrast.
    region = _word_region(half)
    rows = np.zeros_like(mask[region])
    rows[::2] = True
    image[region] = np.where(mask[region] & rows, 255, image[region])
    # Pale ink (contrast 25) against reference ink 0 is not retained.
    region = _word_region(pale)
    image[region] = np.where(mask[region], 230, image[region])
    result = measure(image.astype(np.uint8), mask, page)
    words = result["words"]
    assert words[erased["id"]]["legibility"] == "illegible"
    assert words[half["id"]]["legibility"] == "uncertain", words[half["id"]]
    assert 0.3 <= words[half["id"]]["retention"] < 0.6
    assert words[pale["id"]]["legibility"] == "illegible"
    assert result["page"]["legibility"]["illegible"] == 2


def test_retention_is_relative_to_reference_ink_not_to_the_degraded_word():
    # Uniform grey ink at 200 on paper 240 keeps 40 of the ideal contrast. Against
    # the default reference ink 0 (contrast 240) that is 17 % < 25 %: not retained.
    # Against a declared reference ink 140 (contrast 100) it is 40 %: retained.
    coverage, page = coverage_page()
    mask = ideal_mask(coverage)
    image = np.where(mask, 200, 240).astype(np.uint8)
    default = measure(image, mask, page)
    _, declared_page = coverage_page(contrast={"paper_level": 240, "ink_level": 140})
    declared = measure(image, mask, declared_page)
    word = page["words"][0]["id"]
    assert default["words"][word]["retention"] == 0.0
    assert declared["words"][word]["retention"] == 1.0
    assert default["retention_contrast_share"] == 0.25


def test_exact_polygon_excludes_a_neighbouring_rule_or_word():
    coverage, page = coverage_page()
    mask = ideal_mask(coverage)
    image = identity_image(coverage)
    # A thin rotated word polygon whose bounding box overlaps the next word.
    first, second = page["words"][0], page["words"][1]
    (x0, y0), _, (x1, y1), _ = first["polygon"]
    diagonal = [[x0, y0], [x1 + 10, y0], [x1 + 10, y0 + 2], [x0, y0 + 2]]
    probe = deepcopy(page)
    probe["words"] = [dict(first, polygon=diagonal)]
    pixels = measure(image, mask, probe)["words"][first["id"]]["ink_pixels"]
    box = mask[int(y0):int(y0) + 3, int(x0):int(x1 + 10) + 1].sum()
    assert pixels <= box
    assert second["id"] not in measure(image, mask, probe)["words"]


def test_word_outside_image_or_without_ink_is_handled():
    coverage, page = coverage_page()
    page = deepcopy(page)
    page["words"].append({"id": "ghost", "text": "x", "polygon": [[-50, -50], [-10, -50], [-10, -10], [-50, -10]]})
    page["words"].append({"id": "blank", "text": "y", "polygon": [[480, 60], [500, 60], [500, 80], [480, 80]]})
    result = measure(identity_image(coverage), ideal_mask(coverage), page)
    for wid in ("ghost", "blank"):
        assert result["words"][wid]["ink_pixels"] == 0
        assert result["words"][wid]["legibility"] == "illegible"


def test_measure_is_deterministic_and_json_roundtrip_compares_equal(tmp_path):
    coverage, page = coverage_page()
    params = sample_parameters(load_profile("controlled-v1"), 4)
    page["provenance"]["parameters"]["degradation_profile"] = params
    image, _ = apply(coverage, params)
    mask = ideal_mask(coverage)
    stored = json.loads(json.dumps(measure(image, mask, page)))
    assert compare(stored, measure(image, mask, page)) == []
    stored["page"]["contrast"] += 1
    current = stored["words"]["w000"]["legibility"]
    stored["words"]["w000"]["legibility"] = "readable" if current != "readable" else "illegible"
    del stored["page"]["otsu_threshold"]
    errors = compare(stored, measure(image, mask, page))
    assert len(errors) == 3


def test_label_thresholds_are_declared_boundaries():
    rule = LEGIBILITY_THRESHOLDS["readable"]
    word = {"ink_pixels": rule["min_ink_pixels"], "contrast": rule["min_contrast"], "retention": rule["min_retention"]}
    assert label_legibility(word) == "readable"
    assert label_legibility(dict(word, contrast=rule["min_contrast"] - 0.001)) == "uncertain"
    assert label_legibility(dict(word, retention=0.0)) == "illegible"


def test_mask_png_roundtrip_and_rejections(tmp_path):
    coverage, _ = coverage_page()
    mask = ideal_mask(coverage)
    digest = save_mask(mask, tmp_path / "m.png")
    assert len(digest) == 64
    assert np.array_equal(load_mask(tmp_path / "m.png", mask.shape), mask)
    with pytest.raises(ValueError):
        load_mask(tmp_path / "m.png", (mask.shape[0] + 1, mask.shape[1]))
    Image.fromarray(mask.astype(np.uint8) * 255).save(tmp_path / "grey.png")
    with pytest.raises(ValueError):
        load_mask(tmp_path / "grey.png", mask.shape)


def test_otsu_separates_two_levels():
    image = np.array([[20] * 10 + [230] * 10], dtype=np.uint8)
    threshold = otsu_threshold(image)
    assert 20 <= threshold < 230


def test_rule_coverage_200_is_in_the_mask():
    coverage, _ = coverage_page(rule=True)
    assert ideal_mask(coverage)[-7, 100]


def test_invalid_inputs_are_refused():
    coverage, page = coverage_page()
    with pytest.raises(ValueError):
        measure(identity_image(coverage).astype(np.float32), ideal_mask(coverage), page)
    with pytest.raises(ValueError):
        measure(identity_image(coverage), ideal_mask(coverage)[:-1], page)


def test_document_adds_hashed_input_references_with_fixed_paths():
    from mille_feuilles.diagnostics import diagnostics_path, document, mask_path

    coverage, page = coverage_page()
    page = dict(page, image={"path": "images/fixture.png"})
    image = identity_image(coverage)
    result = document(image, ideal_mask(coverage), page, image_sha256="a" * 64, mask_sha256="b" * 64)
    assert result["inputs"] == {
        "image": {"path": "images/fixture.png", "sha256": "a" * 64},
        "mask": {"path": "qa/masks/fixture.png", "sha256": "b" * 64},
    }
    assert mask_path("mf_0001") == "qa/masks/mf_0001.png"
    assert diagnostics_path("mf_0001") == "qa/diagnostics/mf_0001.json"
    measured = {k: v for k, v in result.items() if k != "inputs"}
    assert compare(measured, measure(image, ideal_mask(coverage), page)) == []
