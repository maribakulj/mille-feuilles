"""Declared, seeded photometric degradations of an ideal ink coverage.

The renderer supplies a float32 coverage in [0, 1] (1 = full ink) that has
already received every geometric transform. This module only changes pixel
values: annotations and the ideal ink mask stay exact. Families are applied in
a fixed order, each from its own random stream, never from the composition RNG.
Profiles are declared intentions, not calibrated models of real scans.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator
from PIL import Image, ImageFilter

from .validation import load_json

PROFILE_FORMAT = "mille-feuilles-degradation-profile"
PROFILE_VERSION = "1"
FAMILIES = ("ink_loss", "contrast", "illumination", "blur", "noise")
PARAM_LIMITS: dict[str, dict[str, tuple[float, float]]] = {
    "ink_loss": {"erosion": (0.0, 1.0), "break_density": (0.0, 0.5), "break_scale_px": (0.5, 8.0)},
    "contrast": {"paper_level": (0, 255), "ink_level": (0, 255)},
    "illumination": {"amplitude": (0, 80), "direction_degrees": (0, 360)},
    "blur": {"sigma_px": (0.0, 5.0)},
    "noise": {"sigma": (0.0, 30.0)},
}
INTEGER_PARAMS: set[tuple[str, str]] = set()
DEFAULT_PAPER, DEFAULT_INK = 255, 0
_HERE = Path(__file__).resolve().parents[2]
PROFILE_DIR = _HERE / "profiles"
SCHEMA_PATH = _HERE / "schemas" / "degradation-profile.schema.json"


class ProfileError(ValueError):
    """A degradation profile or parameter set that cannot be used."""


def _validator() -> Draft202012Validator:
    schema = load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _bounds(distribution: dict) -> tuple[float, float]:
    if "const" in distribution:
        return distribution["const"], distribution["const"]
    if "uniform" in distribution:
        return tuple(distribution["uniform"])
    return min(distribution["choice"]), max(distribution["choice"])


def check_profile(profile: dict) -> dict:
    """Validate an in-memory profile (schema, finiteness, hard limits); return it.

    load_profile() reads a file and calls this function; Config can call it on
    the embedded profile object without a temporary file.
    """
    if not isinstance(profile, dict):
        raise ProfileError("Profil de dégradation : objet JSON attendu")
    try:
        canonical = json.dumps(profile, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProfileError(f"Profil de dégradation non sérialisable en JSON strict : {exc}") from exc
    if json.loads(canonical) != profile:
        raise ProfileError("Profil de dégradation : types non JSON")
    errors = sorted(_validator().iter_errors(profile), key=lambda e: list(map(str, e.path)))
    if errors:
        where = ".".join(map(str, errors[0].path)) or "$"
        raise ProfileError(f"Profil de dégradation invalide ({where}) : {errors[0].message}")
    for family, params in profile["families"].items():
        for name, distribution in params.items():
            low, high = _bounds(distribution)
            limit = PARAM_LIMITS[family][name]
            if "uniform" in distribution and low > high:
                raise ProfileError(f"{family}.{name} : intervalle uniforme inversé")
            if low < limit[0] or high > limit[1]:
                raise ProfileError(f"{family}.{name} : valeurs hors des bornes {limit}")
            if (family, name) in INTEGER_PARAMS and (
                "uniform" in distribution
                or any(not float(v).is_integer() for v in distribution.get("choice", [distribution.get("const", 0)]))
            ):
                raise ProfileError(f"{family}.{name} : valeurs entières (const ou choice) requises")
    contrast = profile["families"].get("contrast")
    if contrast:
        ink = _bounds(contrast.get("ink_level", {"const": DEFAULT_INK}))
        paper = _bounds(contrast.get("paper_level", {"const": DEFAULT_PAPER}))
        if not ink[1] < paper[0]:
            raise ProfileError("contrast : l'encre doit rester strictement plus sombre que le papier")
    return profile



def load_profile(source: str | Path) -> dict:
    """A short name reads profiles/<name>.json of the repository; otherwise a path."""
    if isinstance(source, str) and "/" not in source and not source.endswith(".json"):
        path = PROFILE_DIR / f"{source}.json"
    else:
        path = Path(source)
    try:
        profile = load_json(path)
    except (OSError, ValueError) as exc:
        raise ProfileError(f"Profil de dégradation illisible : {exc}") from exc
    return check_profile(profile)


def profile_sha256(profile: dict) -> str:
    canonical = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def degradation_seed(seed: int, index: int) -> int:
    """Per-page degradation seed, independent of the composition seed."""
    digest = hashlib.sha256(f"mille-feuilles-degrade-v1:{seed}:{index}".encode()).digest()
    return int.from_bytes(digest[:6], "big")


SEED_LIMIT = 2**64


def _check_seed(seed) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < SEED_LIMIT:
        raise ProfileError(f"Graine de dégradation invalide (entier 0..2^64-1) : {seed!r}")
    return seed


def _finite_number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def check_parameters(params: dict) -> dict:
    """Validate resolved parameters (as stored in a page) before applying them."""
    if not isinstance(params, dict):
        raise ProfileError("Paramètres de dégradation : objet attendu")
    unknown = set(params) - {"profile", "profile_sha256", "seed", *FAMILIES}
    if unknown:
        raise ProfileError("Paramètres de dégradation inconnus : " + ", ".join(sorted(map(str, unknown))))
    if not isinstance(params.get("profile"), str) or not isinstance(params.get("profile_sha256"), str) \
            or len(params["profile_sha256"]) != 64:
        raise ProfileError("Paramètres de dégradation : profile et profile_sha256 requis")
    _check_seed(params.get("seed"))
    for family in FAMILIES:
        if family not in params:
            continue
        values = params[family]
        if not isinstance(values, dict):
            raise ProfileError(f"Paramètres {family} : objet attendu")
        for name, value in values.items():
            limit = PARAM_LIMITS[family].get(name)
            if limit is None or not _finite_number(value) or not limit[0] <= value <= limit[1]:
                raise ProfileError(f"Paramètre résolu invalide : {family}.{name}={value!r}")
    paper, ink = reference_levels(params)
    if not ink < paper:
        raise ProfileError("Paramètres de contraste : l'encre doit être plus sombre que le papier")
    return params


def sample_parameters(profile: dict, seed: int) -> dict:
    """Resolve every distribution with a private random.Random(seed)."""
    check_profile(profile)
    rng = random.Random(_check_seed(seed))
    resolved = {"profile": profile["name"], "profile_sha256": profile_sha256(profile), "seed": seed}
    for family in FAMILIES:
        params = profile["families"].get(family)
        if params is None:
            continue
        values = {}
        for name in sorted(params):
            distribution = params[name]
            if "const" in distribution:
                value = distribution["const"]
            elif "uniform" in distribution:
                value = rng.uniform(*distribution["uniform"])
            else:
                value = rng.choice(distribution["choice"])
            if (family, name) in INTEGER_PARAMS:
                value = int(value)
            values[name] = value
        resolved[family] = values
    return resolved


def reference_levels(params: dict) -> tuple[float, float]:
    """(paper, ink) reference levels; an absent contrast family means 255/0."""
    contrast = params.get("contrast", {})
    return float(contrast.get("paper_level", DEFAULT_PAPER)), float(contrast.get("ink_level", DEFAULT_INK))


def downsample_coverage(coverage: np.ndarray, factor: int) -> np.ndarray:
    """Reduce an oversampled grey coverage by an integer factor (exact box mean).

    The ideal mask must be thresholded AFTER this reduction: reducing a boolean
    mask instead would change which pixels count as ink. Height and width must
    be multiples of the factor. Geometry scales by 1/factor (the caller records
    the matrix and transforms the polygons).
    """
    if coverage.ndim != 2 or coverage.dtype != np.float32:
        raise ProfileError("La couverture doit être un tableau float32 à deux dimensions")
    if factor not in (1, 2):
        raise ProfileError("Facteur de suréchantillonnage admis : 1 ou 2")
    height, width = coverage.shape
    if height % factor or width % factor:
        raise ProfileError("Dimensions non multiples du facteur de suréchantillonnage")
    if factor == 1:
        return coverage.copy()
    blocks = coverage.reshape(height // factor, factor, width // factor, factor).astype(np.float64)
    return blocks.mean(axis=(1, 3)).astype(np.float32)


def _stream(seed: int, family: str) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64([seed, FAMILIES.index(family)]))


def _erode(coverage: np.ndarray, radius: int) -> np.ndarray:
    """Grey erosion of the ink coverage (minimum over a (2r+1) square)."""
    padded = np.pad(coverage, radius, mode="constant", constant_values=0.0)
    out = np.ones_like(coverage)
    height, width = coverage.shape
    for dy in range(2 * radius + 1):
        for dx in range(2 * radius + 1):
            np.minimum(out, padded[dy:dy + height, dx:dx + width], out=out)
    return out


def apply(coverage: np.ndarray, params: dict) -> tuple[np.ndarray, list[dict]]:
    """Return the degraded uint8 image (mode L) and one transform per active family."""
    if coverage.ndim != 2 or coverage.dtype != np.float32:
        raise ProfileError("La couverture doit être un tableau float32 à deux dimensions")
    if coverage.size and (not np.isfinite(coverage).all() or coverage.min() < 0 or coverage.max() > 1):
        raise ProfileError("La couverture doit être finie et comprise dans [0, 1]")
    check_parameters(params)
    seed = params["seed"]
    transforms = []

    def record(family: str, **extra) -> None:
        transforms.append({
            "kind": f"mf:degrade:{family}",
            "geometry": "identity",
            "parameters": {**params[family], **extra, "seed": seed, "rng": "numpy.PCG64[seed, family]"},
        })

    cov = coverage.copy()
    if "ink_loss" in params:
        loss = params["ink_loss"]
        # Fractional erosion: blend toward the 3x3 grey erosion. A full 3x3
        # erosion removes most strokes of 20-25 px body text.
        strength = float(loss.get("erosion", 0.0))
        if strength > 0:
            cov = cov - np.float32(strength) * (cov - _erode(cov, 1))
        density = float(loss.get("break_density", 0.0))
        removed = 0
        if density > 0:
            field = _stream(seed, "ink_loss").integers(0, 256, cov.shape, dtype=np.uint8)
            scale = float(loss.get("break_scale_px", 1.0))
            smooth = np.asarray(Image.fromarray(field, "L").filter(ImageFilter.GaussianBlur(scale)))
            inked = cov >= 0.5
            if inked.any():
                cut = np.quantile(smooth[inked], density, method="lower")
                breaks = inked & (smooth <= cut)
                removed = int(breaks.sum())
                cov[breaks] = 0.0
        record("ink_loss", broken_pixels=removed)
    paper, ink = reference_levels(params)
    image = paper - (paper - ink) * cov.astype(np.float64)
    if "contrast" in params:
        record("contrast")
    if "illumination" in params:
        light = params["illumination"]
        theta = math.radians(float(light.get("direction_degrees", 0.0)))
        height, width = cov.shape
        ys, xs = np.mgrid[0:height, 0:width]
        t = xs * math.cos(theta) + ys * math.sin(theta)
        span = t.max() - t.min()
        if span > 0:
            image = image + float(light.get("amplitude", 0.0)) * ((t - t.min()) / span - 0.5)
        record("illumination")
    image = np.clip(np.rint(image), 0, 255).astype(np.uint8)
    if "blur" in params:
        sigma = float(params["blur"].get("sigma_px", 0.0))
        if sigma > 0:
            image = np.asarray(Image.fromarray(image, "L").filter(ImageFilter.GaussianBlur(sigma)))
        record("blur", implementation="Pillow GaussianBlur on 8-bit image")
    if "noise" in params:
        sigma = float(params["noise"].get("sigma", 0.0))
        if sigma > 0:
            noise = _stream(seed, "noise").normal(0.0, sigma, image.shape)
            image = np.clip(np.rint(image + noise), 0, 255).astype(np.uint8)
        record("noise")
    return np.ascontiguousarray(image, dtype=np.uint8), transforms
