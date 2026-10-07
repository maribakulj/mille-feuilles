"""Declared degradation profiles: strict loading, private seeds, exact effects."""

import json
import random
from copy import deepcopy

import numpy as np
import pytest
from test_diagnostics import coverage_page

from mille_feuilles import degrade
from mille_feuilles.degrade import (
    FAMILIES,
    ProfileError,
    apply,
    degradation_seed,
    downsample_coverage,
    load_profile,
    profile_sha256,
    sample_parameters,
    check_profile,
)
from mille_feuilles.diagnostics import ideal_mask, measure


def controlled():
    return load_profile("controlled-v1")


def single(family, **values):
    """A profile with one family and constant parameters."""
    profile = deepcopy(load_profile("identity"))
    profile["name"] = "single"
    profile["families"] = {family: {k: {"const": v} for k, v in values.items()}}
    return profile


def test_shipped_profiles_load_and_are_declared_uncalibrated():
    for name in ("controlled-v1", "identity"):
        profile = load_profile(name)
        assert profile["calibrated"] is False and profile["oversampling"] == 1
    assert set(controlled()["families"]) == set(FAMILIES)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(format="other"),
        lambda p: p.update(version="2"),
        lambda p: p.update(oversampling=3),
        lambda p: p.pop("calibrated"),
        lambda p: p.update(calibrated=True),
        lambda p: p.update(calibrated="false"),
        lambda p: p.update(extra=1),
        lambda p: p["families"].update(verso={"alpha": {"const": 0.1}}),
        lambda p: p["families"]["blur"].update(radius={"const": 1}),
        lambda p: p["families"]["blur"].update(sigma_px={"uniform": [1.0, 0.5]}),
        lambda p: p["families"]["blur"].update(sigma_px={"uniform": [0.0, 9.0]}),
        lambda p: p["families"]["noise"].update(sigma={"choice": []}),
        lambda p: p["families"]["noise"].update(sigma={"const": 1, "uniform": [0, 1]}),
        lambda p: p["families"]["ink_loss"].update(erosion={"uniform": [0.0, 1.5]}),
        lambda p: p["families"]["ink_loss"].update(erosion_px={"const": 1}),
        lambda p: p["families"]["contrast"].update(ink_level={"uniform": [100, 240]}),
        lambda p: p["families"].update(blur={}),
    ],
)
def test_invalid_profiles_are_refused(tmp_path, mutate):
    profile = deepcopy(controlled())
    mutate(profile)
    path = tmp_path / "p.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ProfileError):
        load_profile(path)


def test_duplicate_json_keys_are_refused(tmp_path):
    path = tmp_path / "p.json"
    path.write_text('{"format": "a", "format": "b"}', encoding="utf-8")
    with pytest.raises(ProfileError):
        load_profile(path)


def test_degradation_seed_is_independent_of_composition_seed():
    from mille_feuilles.render import page_seed

    assert degradation_seed(20261007, 3) != page_seed(20261007, 3)
    assert degradation_seed(1, 0) == degradation_seed(1, 0) != degradation_seed(1, 1)


def test_sampling_uses_a_private_rng_and_is_deterministic():
    random.seed(123)
    before = random.random()
    random.seed(123)
    first = sample_parameters(controlled(), 42)
    assert random.random() == before  # the global/composition RNG did not move
    assert sample_parameters(controlled(), 42) == first != sample_parameters(controlled(), 43)
    assert first["profile_sha256"] == profile_sha256(controlled())
    for family, params in first.items():
        if family in FAMILIES:
            for name, value in params.items():
                low, high = degrade.PARAM_LIMITS[family][name]
                assert low <= value <= high


def test_identity_profile_is_paper_255_and_ink_0_without_transforms():
    coverage, _ = coverage_page()
    params = sample_parameters(load_profile("identity"), 7)
    image, transforms = apply(coverage, params)
    assert transforms == []
    assert np.array_equal(image, np.rint(255 - 255 * coverage.astype(np.float64)).astype(np.uint8))


def test_same_inputs_give_same_bytes_and_one_record_per_active_family():
    coverage, _ = coverage_page()
    params = sample_parameters(controlled(), 9)
    one, transforms = apply(coverage, params)
    two, _ = apply(coverage, params)
    assert one.tobytes() == two.tobytes() and one.dtype == np.uint8
    assert [t["kind"] for t in transforms] == [f"mf:degrade:{f}" for f in FAMILIES]
    assert all(t["geometry"] == "identity" and t["parameters"]["seed"] == 9 for t in transforms)


def test_input_coverage_is_not_modified():
    coverage, _ = coverage_page()
    original = coverage.copy()
    apply(coverage, sample_parameters(single("ink_loss", erosion=1.0, break_density=0.2, break_scale_px=2), 1))
    assert np.array_equal(coverage, original)


@pytest.mark.parametrize(
    "coverage",
    [np.zeros((4, 4), np.float64), np.full((4, 4), 1.5, np.float32), np.full((4, 4), np.nan, np.float32),
     np.zeros((4, 4, 3), np.float32)],
)
def test_invalid_coverage_is_refused(coverage):
    with pytest.raises(ProfileError):
        apply(coverage, sample_parameters(load_profile("identity"), 0))


def test_tampered_resolved_parameters_are_refused():
    coverage, _ = coverage_page()
    params = sample_parameters(controlled(), 3)
    params["blur"]["sigma_px"] = 50
    with pytest.raises(ProfileError):
        apply(coverage, params)


# Controlled one-parameter sweeps on a fixed coverage (no universal claim).


def _measure(profile, seed=0, contrast=None):
    coverage, page = coverage_page(contrast=contrast)
    params = sample_parameters(profile, seed)
    if contrast is None and "contrast" in params:
        page["provenance"]["parameters"]["degradation_profile"] = params
    image, _ = apply(coverage, params)
    return measure(image, ideal_mask(coverage), page)


def test_lighter_ink_lowers_measured_contrast_strictly():
    values = [
        _measure(single("contrast", paper_level=240, ink_level=ink))["page"]["contrast"]
        for ink in (10, 60, 110, 160)
    ]
    assert values == sorted(values, reverse=True) and len(set(values)) == 4


def test_erosion_does_not_decrease_ink_loss():
    losses = [
        _measure(single("ink_loss", erosion=e))["page"]["ink_loss_fraction"] for e in (0.0, 0.5, 1.0)
    ]
    assert losses == sorted(losses) and losses[0] == 0.0 < losses[2]


def test_more_breaks_do_not_increase_mean_retention_at_fixed_seed():
    means = []
    for density in (0.0, 0.1, 0.3):
        words = _measure(single("ink_loss", break_density=density, break_scale_px=2.0), seed=5)["words"]
        means.append(sum(w["retention"] for w in words.values()) / len(words))
    assert means == sorted(means, reverse=True) and means[0] > means[2]


def test_break_density_removes_the_declared_fraction_of_inked_pixels():
    coverage, _ = coverage_page()
    params = sample_parameters(single("ink_loss", break_density=0.25, break_scale_px=1.5), 2)
    _, transforms = apply(coverage, params)
    inked = int((coverage >= 0.5).sum())
    removed = transforms[0]["parameters"]["broken_pixels"]
    assert abs(removed / inked - 0.25) < 0.05


def test_zero_noise_measures_zero_noise_and_noise_is_measured():
    def profile(sigma):
        value = single("noise", sigma=sigma)
        value["families"]["contrast"] = {"paper_level": {"const": 230}, "ink_level": {"const": 30}}
        return value

    assert _measure(profile(0.0))["page"]["noise_mad_sigma"] == 0.0
    measured = _measure(profile(8.0), seed=1)["page"]["noise_mad_sigma"]
    assert 6.0 < measured < 10.0


def test_noise_on_white_paper_is_clipped_and_underestimated():
    # Documented limit: at paper 255 half of the noise is clipped, MAD collapses.
    assert _measure(single("noise", sigma=8.0), seed=1)["page"]["noise_mad_sigma"] < 4.0


def test_photometric_effects_never_move_the_ideal_mask():
    coverage, page = coverage_page()
    mask = ideal_mask(coverage)
    image, _ = apply(coverage, sample_parameters(controlled(), 11))
    assert image.shape == coverage.shape
    assert np.array_equal(ideal_mask(coverage), mask)


def test_downsampling_reduces_grey_coverage_before_thresholding():
    # 2x2 blocks with 2 inked subpixels of 4: grey 0.5 -> ink after reduction.
    # A boolean mask reduced by majority/any rule would decide differently.
    fine = np.zeros((4, 4), np.float32)
    fine[0, 0] = fine[0, 1] = 1.0          # block (0,0): mean 0.5
    fine[2, 2] = 1.0                       # block (1,1): mean 0.25
    reduced = downsample_coverage(fine, 2)
    assert reduced.dtype == np.float32 and reduced.shape == (2, 2)
    assert reduced.tolist() == [[0.5, 0.0], [0.0, 0.25]]
    assert ideal_mask(reduced).tolist() == [[True, False], [False, False]]
    any_rule = (fine >= 0.5).reshape(2, 2, 2, 2).any(axis=(1, 3))
    assert any_rule.tolist() != ideal_mask(reduced).tolist()


def test_downsampling_rejects_bad_inputs_and_is_identity_at_factor_1():
    coverage, _ = coverage_page(width=520, height=150)
    assert np.array_equal(downsample_coverage(coverage, 1), coverage)
    with pytest.raises(ProfileError):
        downsample_coverage(coverage, 3)
    with pytest.raises(ProfileError):
        downsample_coverage(np.zeros((5, 4), np.float32), 2)
    with pytest.raises(ProfileError):
        downsample_coverage(np.zeros((4, 4), np.float64), 2)


def test_check_profile_accepts_in_memory_objects_without_a_file():
    profile = deepcopy(controlled())
    assert check_profile(profile) is profile


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), True, "1.0", None],
)
def test_check_profile_rejects_non_finite_or_non_numeric_values(value):
    profile = deepcopy(controlled())
    profile["families"]["blur"]["sigma_px"] = {"const": value}
    with pytest.raises(ProfileError):
        check_profile(profile)


@pytest.mark.parametrize("profile", [None, [], "controlled-v1", {"families": {1: {}}}])
def test_check_profile_rejects_non_profile_objects(profile):
    with pytest.raises(ProfileError):
        check_profile(profile)


def _hostile(mutate):
    params = sample_parameters(controlled(), 1)
    mutate(params)
    return params


@pytest.mark.parametrize(
    "mutate",
    [
        lambda q: q["blur"].update(sigma_px=10**400),
        lambda q: q["blur"].update(sigma_px=float("nan")),
        lambda q: q["noise"].update(sigma=True),
        lambda q: q.update(seed=-1),
        lambda q: q.update(seed=2**64),
        lambda q: q.update(seed="1"),
        lambda q: q.update(seed=True),
        lambda q: q.pop("seed"),
        lambda q: q.pop("profile_sha256"),
        lambda q: q.update(verso={"alpha": 0.1}),
        lambda q: q.update(blur=3),
        lambda q: q["contrast"].update(ink_level=250, paper_level=10),
    ],
)
def test_apply_refuses_hostile_resolved_parameters_with_profile_error(mutate):
    coverage, _ = coverage_page()
    with pytest.raises(ProfileError):
        apply(coverage, _hostile(mutate))


@pytest.mark.parametrize("seed", [-1, 2**64, 10**400, "x", True, 1.5, None])
def test_sample_parameters_refuses_invalid_seeds(seed):
    with pytest.raises(ProfileError):
        sample_parameters(controlled(), seed)


@pytest.mark.parametrize("value", [10**400, -(10**400)])
def test_huge_integers_in_a_profile_are_refused(value):
    profile = deepcopy(controlled())
    profile["families"]["blur"]["sigma_px"] = {"uniform": [0, value]} if value > 0 else {"const": value}
    with pytest.raises(ProfileError):
        check_profile(profile)


def test_largest_valid_seed_is_accepted():
    coverage, _ = coverage_page()
    image, _ = apply(coverage, sample_parameters(controlled(), 2**64 - 1))
    assert image.dtype == np.uint8


def test_calibrated_true_is_refused_before_any_generation():
    profile = deepcopy(controlled())
    profile["calibrated"] = True
    with pytest.raises(ProfileError, match="calibrated"):
        check_profile(profile)
