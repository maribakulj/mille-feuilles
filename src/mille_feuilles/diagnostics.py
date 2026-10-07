"""Deterministic measurements of a final page image against its ideal ink mask.

The mask is the ideal coverage (>= 0.5) after geometric transforms only, so
ink lost or added by photometric degradations remains measurable. Legibility
labels are heuristics with declared thresholds; they are not evidence of human
reading. All values are recomputable from the image, the mask and the page.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
from PIL import Image, ImageDraw

DIAGNOSTICS_FORMAT = "mille-feuilles-diagnostics"
DIAGNOSTICS_VERSION = "1"
LEGIBILITY_METHOD = "heuristic-v1"
MASK_THRESHOLD = 0.5
PAPER_MARGIN_PX = 2
MIN_LOCAL_PAPER = 16
# A mask pixel is retained when it keeps at least this share of the ideal
# paper-ink contrast of its word (local paper, declared reference ink).
RETENTION_CONTRAST_SHARE = 0.25
LEGIBILITY_THRESHOLDS = {
    "readable": {"min_contrast": 40.0, "min_retention": 0.60, "min_ink_pixels": 2},
    "uncertain": {"min_contrast": 20.0, "min_retention": 0.30, "min_ink_pixels": 1},
}
_DIGITS = 6
MASK_PATH = "qa/masks/{page_id}.png"
DIAGNOSTICS_PATH = "qa/diagnostics/{page_id}.json"


def mask_path(page_id: str) -> str:
    return MASK_PATH.format(page_id=page_id)


def diagnostics_path(page_id: str) -> str:
    return DIAGNOSTICS_PATH.format(page_id=page_id)


def ideal_mask(coverage: np.ndarray) -> np.ndarray:
    return np.asarray(coverage) >= MASK_THRESHOLD


def save_mask(mask: np.ndarray, path) -> str:
    """Write a 1-bit PNG (white = ink) and return its SHA-256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(mask, dtype=bool)).save(path, optimize=True)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mask(path, shape: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as image:
        if image.format != "PNG" or image.mode != "1" or image.size != (shape[1], shape[0]):
            raise ValueError("Masque d'encre : PNG 1 bit aux dimensions de l'image attendu")
        return np.asarray(image, dtype=bool)


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    padded = np.pad(mask, radius, mode="constant", constant_values=False)
    out = np.zeros_like(mask)
    height, width = mask.shape
    for dy in range(2 * radius + 1):
        for dx in range(2 * radius + 1):
            out |= padded[dy:dy + height, dx:dx + width]
    return out


def _erode(mask: np.ndarray, radius: int) -> np.ndarray:
    return ~_dilate(~mask, radius)


def otsu_threshold(image: np.ndarray) -> int:
    """Smallest level maximizing between-class variance; dark class is <= threshold."""
    hist = np.bincount(image.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 0
    levels = np.arange(256, dtype=np.float64)
    weight = np.cumsum(hist)
    mass = np.cumsum(hist * levels)
    background = total - weight
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mass[-1] * weight - mass * total) ** 2 / (weight * background)
    between[(weight == 0) | (background == 0)] = -1.0
    return int(np.argmax(between))


def _round(value: float) -> float:
    value = float(value)
    return round(value, _DIGITS) if math.isfinite(value) else 0.0


def _median(values: np.ndarray, default: float) -> float:
    return float(np.median(values)) if values.size else float(default)


def reference_levels(page: dict) -> tuple[float, float]:
    """Ideal (paper, ink) from the resolved profile; absent contrast means 255/0."""
    from .degrade import check_parameters
    from .degrade import reference_levels as resolved_levels

    resolved = page["provenance"]["parameters"].get("degradation_profile")
    if resolved is None:
        return 255.0, 0.0
    return resolved_levels(check_parameters(resolved))


def label_legibility(word: dict) -> str:
    for label in ("readable", "uncertain"):
        rule = LEGIBILITY_THRESHOLDS[label]
        if (
            word["ink_pixels"] >= rule["min_ink_pixels"]
            and word["contrast"] >= rule["min_contrast"]
            and word["retention"] >= rule["min_retention"]
        ):
            return label
    return "illegible"


def _polygon_mask(polygon, x0: int, y0: int, width: int, height: int) -> np.ndarray:
    canvas = Image.new("1", (width, height), 0)
    ImageDraw.Draw(canvas).polygon([(x - x0, y - y0) for x, y in polygon], fill=1, outline=1)
    return np.asarray(canvas, dtype=bool)


def measure(image: np.ndarray, mask: np.ndarray, page: dict) -> dict:
    """Page and word diagnostics; same inputs give identical output."""
    image = np.asarray(image)
    mask = np.asarray(mask, dtype=bool)
    if image.ndim != 2 or image.dtype != np.uint8 or mask.shape != image.shape:
        raise ValueError("Image uint8 à deux dimensions et masque de même forme attendus")
    paper_ref, ink_ref = reference_levels(page)
    near_ink = _dilate(mask, PAPER_MARGIN_PX)
    paper_pixels = image[~near_ink]
    ink_pixels = image[mask]
    paper_median = _median(paper_pixels, paper_ref)
    ink_median = _median(ink_pixels, ink_ref)
    contrast = paper_median - ink_median
    threshold = otsu_threshold(image)
    noise = 1.4826 * _median(np.abs(paper_pixels.astype(np.float64) - paper_median), 0.0)
    boundary = mask & ~_erode(mask, 1)
    grey = image.astype(np.float64)
    gy, gx = np.gradient(grey)
    edge = float(np.hypot(gx, gy)[boundary].mean()) if boundary.any() else 0.0
    words, counts = {}, {"readable": 0, "uncertain": 0, "illegible": 0}
    height, width = image.shape
    for word in page["words"]:
        xs = [p[0] for p in word["polygon"]]
        ys = [p[1] for p in word["polygon"]]
        # Clip to the image; a polygon outside it yields an empty region, never a
        # negative (wrapping) slice.
        x0 = min(width, max(0, math.floor(min(xs))))
        y0 = min(height, max(0, math.floor(min(ys))))
        x1 = max(x0, min(width, math.ceil(max(xs)) + 1))
        y1 = max(y0, min(height, math.ceil(max(ys)) + 1))
        if x1 > x0 and y1 > y0:
            inside = _polygon_mask(word["polygon"], x0, y0, x1 - x0, y1 - y0)
        else:
            inside = np.zeros((y1 - y0, x1 - x0), dtype=bool)
        region = image[y0:y1, x0:x1]
        word_ink = inside & mask[y0:y1, x0:x1]
        word_paper = inside & ~near_ink[y0:y1, x0:x1]
        local_paper = region[word_paper]
        paper = _median(local_paper, paper_median) if local_paper.size >= MIN_LOCAL_PAPER else paper_median
        inked = region[word_ink]
        if inked.size:
            ink = float(np.percentile(inked, 10))
            cut = paper - RETENTION_CONTRAST_SHARE * (paper - ink_ref)
            retention = float(np.mean(inked <= cut))
        else:
            ink, retention = paper, 0.0
        item = {
            "ink_pixels": int(inked.size),
            "paper": _round(paper),
            "ink": _round(ink),
            "contrast": _round(paper - ink),
            "retention": _round(retention),
        }
        item["legibility"] = label_legibility(item)
        counts[item["legibility"]] += 1
        words[word["id"]] = item
    return {
        "format": DIAGNOSTICS_FORMAT,
        "version": DIAGNOSTICS_VERSION,
        "page_id": page["page_id"],
        "legibility_method": LEGIBILITY_METHOD,
        "thresholds": LEGIBILITY_THRESHOLDS,
        "retention_contrast_share": RETENTION_CONTRAST_SHARE,
        "references": {"paper_level": _round(paper_ref), "ink_level": _round(ink_ref)},
        "page": {
            "ink_pixels": int(mask.sum()),
            "paper_median": _round(paper_median),
            "ink_median": _round(ink_median),
            "contrast": _round(contrast),
            "otsu_threshold": threshold,
            "ink_loss_fraction": _round(np.mean(ink_pixels > threshold) if ink_pixels.size else 0.0),
            "spurious_ink_fraction": _round(np.mean(paper_pixels <= threshold) if paper_pixels.size else 0.0),
            "noise_mad_sigma": _round(noise),
            "edge_contrast_proxy": _round(edge / contrast if contrast > 0 else 0.0),
            "legibility": counts,
        },
        "words": words,
    }


def document(
    image: np.ndarray, mask: np.ndarray, page: dict, *, image_sha256: str, mask_sha256: str
) -> dict:
    """The diagnostics file: measure() plus hashed references to its two inputs.

    The validator recomputes it from the files named here and calls compare().
    """
    result = measure(image, mask, page)
    result["inputs"] = {
        "image": {"path": page["image"]["path"], "sha256": image_sha256},
        "mask": {"path": mask_path(page["page_id"]), "sha256": mask_sha256},
    }
    return result


def compare(stored: dict, recomputed: dict, path: str = "$") -> list[str]:
    """Exact comparison of a stored diagnostics document with a recomputation."""
    if isinstance(stored, dict) and isinstance(recomputed, dict):
        errors = [f"{path}.{k}: absent du recalcul" for k in sorted(set(stored) - set(recomputed))]
        errors += [f"{path}.{k}: absent du fichier" for k in sorted(set(recomputed) - set(stored))]
        for key in sorted(set(stored) & set(recomputed)):
            errors += compare(stored[key], recomputed[key], f"{path}.{key}")
        return errors
    if type(stored) is not type(recomputed) and not (
        isinstance(stored, (int, float)) and isinstance(recomputed, (int, float))
        and not isinstance(stored, bool) and not isinstance(recomputed, bool)
    ):
        return [f"{path}: type différent"]
    if isinstance(stored, list):
        if len(stored) != len(recomputed):
            return [f"{path}: longueur différente"]
        return [e for i, (a, b) in enumerate(zip(stored, recomputed)) for e in compare(a, b, f"{path}[{i}]")]
    return [] if stored == recomputed else [f"{path}: {stored!r} ≠ {recomputed!r}"]
