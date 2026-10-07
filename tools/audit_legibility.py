"""Audit final word pixels without OCR, reading the dataset without modifying it.

The fixed thresholds detect absent/faint/tiny rendered content, not recognition
accuracy. Reports and optional native-resolution sample sheets must be written
outside the dataset, to new destinations. Run from the installed checkout:
  python tools/audit_legibility.py LOT --report /outside/audit.json
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from mille_feuilles.io import sha256
from mille_feuilles.validation import load_json, safe_path

THRESHOLDS = {
    "minimum_contrast_gray_levels": 40.0,
    "minimum_ink_pixels": 2,
    "minimum_effective_font_size_px": 10.0,
    "background_percentile": 90.0,
    "local_padding_px": 3,
}
LIMITATIONS = [
    "Presence and contrast of ink are not proof of human readability or OCR recognition.",
    "One visible component does not prove that every character of a word is intact.",
    "The local background is estimated from pixels around the final word polygon.",
    "The audit does not establish historical realism or a gain on real documents.",
    "Sample sheets require visual review; their creation is not visual acceptance.",
]


def _output_path(path: Path, root: Path, kind: str) -> Path:
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"{kind} must be a new path, not a symlink: {path}")
    resolved = path.resolve()
    if resolved.is_relative_to(root):
        raise ValueError(f"{kind} must be outside the dataset: {resolved}")
    if resolved.exists():
        raise ValueError(f"{kind} already exists; choose a new destination: {resolved}")
    return resolved


def _effective_scale(page: dict) -> float:
    linear = np.eye(2)
    for transform in page["transforms"]:
        geometry = transform["geometry"]
        if geometry != "identity":
            matrix = np.asarray(geometry["matrix"], dtype=float)
            if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
                raise ValueError("invalid affine matrix")
            if not np.allclose(matrix[2], [0, 0, 1], atol=1e-12, rtol=0):
                raise ValueError("non-affine transformation")
            linear = matrix[:2, :2] @ linear
    scale = float(np.linalg.svd(linear, compute_uv=False).min())
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("non-invertible affine scale")
    return scale


def measure_word(pixels: np.ndarray, word: dict, font_size: float | None, scale: float) -> dict:
    """Measure the actual final raster within the word's final polygon."""
    points = np.asarray(word["polygon"], dtype=float)
    if points.ndim != 2 or points.shape[0] < 3 or points.shape[1] != 2:
        raise ValueError("word polygon needs at least three 2D vertices")
    if not np.isfinite(points).all():
        raise ValueError("non-finite word geometry")
    height, width = pixels.shape
    xmin, ymin = points.min(axis=0)
    xmax, ymax = points.max(axis=0)
    if xmin < 0 or ymin < 0 or xmax > width or ymax > height or xmin >= xmax or ymin >= ymax:
        raise ValueError("word polygon outside image or degenerate")
    padding = THRESHOLDS["local_padding_px"]
    left, top = max(0, math.floor(xmin) - padding), max(0, math.floor(ymin) - padding)
    right = min(width, math.ceil(xmax) + padding)
    bottom = min(height, math.ceil(ymax) + padding)
    patch = pixels[top:bottom, left:right]
    mask_image = Image.new("1", (right - left, bottom - top))
    ImageDraw.Draw(mask_image).polygon([(x - left, y - top) for x, y in points], fill=1)
    mask = np.asarray(mask_image, dtype=bool)
    values = patch[mask]
    if values.size == 0:
        raise ValueError("word polygon covers no final pixels")
    surrounding = patch[~mask]
    background = float(
        np.percentile(
            surrounding if surrounding.size else patch, THRESHOLDS["background_percentile"]
        )
    )
    contrast = max(0.0, background - float(values.min()))
    ink_pixels = int(
        np.count_nonzero(
            background - values.astype(float) >= THRESHOLDS["minimum_contrast_gray_levels"]
        )
    )
    effective_size = font_size * scale if font_size is not None else None
    reasons = []
    if contrast < THRESHOLDS["minimum_contrast_gray_levels"]:
        reasons.append("contrast_below_40")
    if ink_pixels < THRESHOLDS["minimum_ink_pixels"]:
        reasons.append("fewer_than_2_ink_pixels")
    if effective_size is None:
        reasons.append("font_size_missing")
    elif effective_size + 1e-6 < THRESHOLDS["minimum_effective_font_size_px"]:
        reasons.append("effective_font_size_below_10_px")
    return {
        "background_gray": round(background, 4),
        "contrast_gray_levels": round(contrast, 4),
        "ink_pixels": ink_pixels,
        "polygon_pixels": int(values.size),
        "font_size_px": font_size,
        "effective_font_size_px": round(effective_size, 6) if effective_size is not None else None,
        "bbox_width_px": round(float(xmax - xmin), 6),
        "bbox_height_px": round(float(ymax - ymin), 6),
        "crop_box": [left, top, right, bottom],
        "reasons": reasons,
    }


def _candidate(candidates: dict, key: str, record: dict, rank: tuple) -> None:
    if key not in candidates or rank < candidates[key][0]:
        candidates[key] = (rank, record)


def _choose_samples(candidates_by_page: list[dict], maximum: int) -> list[dict]:
    selected = {}

    def add(record, reason):
        key = record["page_id"], record["word_id"]
        if key in selected:
            if reason not in selected[key]["selection_reasons"]:
                selected[key]["selection_reasons"].append(reason)
        elif len(selected) < maximum:
            selected[key] = {**record, "selection_reasons": [reason]}

    # For a 100-page pilot and a budget of 150, every page receives one lexical
    # sample before special cases. The remaining slots cover explicit strata.
    for candidates in candidates_by_page:
        choice = candidates.get("lexical") or candidates.get("contrast")
        if choice:
            add(choice[1], "page_representative_low_contrast_lexical_word")
    all_records = [item[1] for c in candidates_by_page for item in c.values()]
    if all_records:
        add(
            min(all_records, key=lambda r: (r["angle_degrees"], r["page_id"])),
            "minimum_rotation_angle",
        )
        add(
            max(all_records, key=lambda r: (r["angle_degrees"], r["page_id"])),
            "maximum_rotation_angle",
        )
    for kind in (
        "punctuation",
        "hyphen_start",
        "hyphen_end",
        "font",
        "contrast",
        "title",
        "advertisement",
    ):
        buckets = {}
        for candidates in candidates_by_page:
            if kind not in candidates:
                continue
            rank, record = candidates[kind]
            stratum = record["columns"], record["degradation"]
            if stratum not in buckets or rank < buckets[stratum][0]:
                buckets[stratum] = (rank, record)
        for stratum in sorted(buckets):
            add(buckets[stratum][1], f"{kind}:columns={stratum[0]},mode={stratum[1]}")
    for record in sorted(
        all_records,
        key=lambda r: (
            not bool(r["reasons"]),
            r["contrast_gray_levels"],
            r["page_id"],
            r["word_id"],
        ),
    ):
        add(record, "additional_low_contrast_or_suspect")
    return sorted(selected.values(), key=lambda r: (r["page_id"], r["word_id"]))


def _caption_font(root: Path):
    try:
        manifest = load_json(safe_path(root, "manifest.json"))
        registry = load_json(safe_path(root, manifest["assets"]["path"]))
        candidates = [a for a in registry["assets"] if a["kind"] == "font"]
        candidates.sort(key=lambda a: ("Regular" not in a["path"], a["path"]))
        for asset in candidates:
            try:
                return ImageFont.truetype(safe_path(root, asset["path"]), 18)
            except (OSError, ValueError):
                pass
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return ImageFont.load_default(size=18)


def _text_rows(text: str, font, width: int) -> list[str]:
    rows, current = [], ""
    for character in text:
        if current and font.getlength(current + character) > width:
            rows.append(current)
            current = ""
        current += character
    if current:
        rows.append(current)
    return rows or [""]


def _write_samples(root: Path, directory: Path, samples: list[dict]) -> list[dict]:
    """Use native pixels or nearest-neighbour x2, never downsample word crops."""
    directory.mkdir(parents=True, exist_ok=False)
    font = _caption_font(root)
    sheets, cards = [], []
    card_width, card_height = 800, 250

    def flush():
        if not cards:
            return
        number = len(sheets)
        canvas = Image.new(
            "RGB", (card_width * 2, card_height * math.ceil(len(cards) / 2)), "#e8e8e8"
        )
        entries = []
        for index, (card, sample, tile) in enumerate(cards):
            canvas.paste(card, ((index % 2) * card_width, (index // 2) * card_height))
            entries.append(
                {
                    "page_id": sample["page_id"],
                    "word_id": sample["word_id"],
                    "card_index": index,
                    "tile_index": tile,
                }
            )
        path = directory / f"samples_{number:02d}.png"
        canvas.save(path, compress_level=6)
        sheets.append({"path": str(path), "sha256": sha256(path), "cards": entries})
        cards.clear()

    current_page, page_image = None, None
    try:
        for sample in samples:
            if sample["page_id"] != current_page:
                if page_image is not None:
                    page_image.close()
                with Image.open(safe_path(root, sample["image_path"])) as image:
                    page_image = image.convert("RGB")
                current_page = sample["page_id"]
            crop = page_image.crop(sample["crop_box"])
            enlargement = 2 if crop.width * 2 <= 768 and crop.height * 2 <= 154 else 1
            if enlargement == 2:
                crop = crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.NEAREST)
            tile_boxes = [
                (x, y, min(x + 768, crop.width), min(y + 154, crop.height))
                for y in range(0, crop.height, 154)
                for x in range(0, crop.width, 768)
            ]
            sample["display_scale"] = enlargement
            sample["display_tile_count"] = len(tile_boxes)
            for tile_index, box in enumerate(tile_boxes):
                card = Image.new("RGB", (card_width, card_height), "white")
                drawing = ImageDraw.Draw(card)
                label = f"{sample['page_id']} / {sample['word_id']} / {sample['degradation']} / {sample['columns']} col."
                drawing.text((12, 5), label, fill="black", font=font)
                detail = (
                    f"contraste {sample['contrast_gray_levels']:.1f} ; encre {sample['ink_pixels']} px ; "
                    f"police {sample['effective_font_size_px']} px ; x{enlargement}"
                )
                drawing.text((12, 27), detail, fill="black", font=font)
                # Very long words are tiled; captions are split alongside them
                # instead of silently reducing the final raster below native size.
                rows = _text_rows(sample["text"], font, 770)
                caption = rows[min(tile_index, len(rows) - 1)]
                drawing.text((12, 49), caption, fill="#003b6b", font=font)
                if len(tile_boxes) > 1:
                    drawing.text(
                        (12, 71),
                        f"Extrait {tile_index + 1}/{len(tile_boxes)} ; texte complet dans le rapport",
                        fill="#555555",
                        font=font,
                    )
                card.paste(crop.crop(box), (12, 94))
                cards.append((card, sample, tile_index))
                if len(cards) == 10:
                    flush()
    finally:
        if page_image is not None:
            page_image.close()
    flush()
    return sheets


def audit_legibility(
    root: Path, report_path: Path, samples_dir: Path | None = None, max_samples: int = 150
) -> dict:
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"Dataset directory does not exist: {root}")
    if not 0 <= max_samples <= 150:
        raise ValueError("max_samples must be between 0 and 150")
    report_path = _output_path(report_path, root, "Report")
    samples_dir = (
        _output_path(samples_dir, root, "Sample directory") if samples_dir is not None else None
    )
    if samples_dir is not None and report_path.is_relative_to(samples_dir):
        raise ValueError("Report and sample directory must be separate destinations")
    report = {
        "audit_version": "1.0.0",
        "dataset_root": str(root),
        "status": "fail",
        "thresholds": dict(THRESHOLDS),
        "limitations": list(LIMITATIONS),
        "errors": [],
        "pages": [],
        "suspects": [],
        "samples": [],
        "sample_sheets": [],
    }
    candidates_by_page = []
    page_ids = set()
    total_words = 0
    measured_words = 0
    try:
        manifest_path = safe_path(root, "manifest.json")
        manifest = load_json(manifest_path)
        report["manifest_sha256"] = sha256(manifest_path)
        report["dataset_id"] = manifest["dataset_id"]
        if manifest["schema_version"] != "0.2.0" or not isinstance(manifest["pages"], list):
            raise ValueError("Expected a version 0.2.0 manifest and page list")
        records = manifest["pages"]
        if not records:
            raise ValueError("Dataset has no pages")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["errors"].append(f"manifest: {exc}")
        records = []
    for reference in records:
        page_id = reference.get("id", "unknown") if isinstance(reference, dict) else "unknown"
        try:
            page_path = safe_path(root, reference["path"])
            if sha256(page_path) != reference["sha256"]:
                report["errors"].append(f"{page_id}: annotation SHA-256 mismatch")
            page = load_json(page_path)
            if page["page_id"] != page_id or page_id in page_ids:
                raise ValueError("page identity mismatch or duplicate page")
            page_ids.add(page_id)
            params = page["provenance"]["parameters"]
            scale = _effective_scale(page)
            image_path = safe_path(root, page["image"]["path"])
            if sha256(image_path) != page["image"]["sha256"]:
                report["errors"].append(f"{page_id}: image SHA-256 mismatch")
            with Image.open(image_path) as image:
                if image.format != "PNG" or image.size != (
                    page["image"]["width"],
                    page["image"]["height"],
                ):
                    raise ValueError("PNG dimensions/format differ from annotation")
                pixels = np.asarray(image.convert("L")).copy()
            lines = {line["id"]: line for line in page["lines"]}
            blocks = {block["id"]: block for block in page["blocks"]}
            candidates = {}
            measurements = []
            seen_words = set()
            font_sizes = Counter()
            word_count = len(page["words"])
            total_words += word_count
            if not word_count:
                raise ValueError("page contains no words")
            for word in page["words"]:
                word_id = word.get("id", "unknown")
                try:
                    if word_id in seen_words:
                        raise ValueError("duplicate word identity")
                    seen_words.add(word_id)
                    line = lines[word["line_id"]]
                    block = blocks[line["block_id"]]
                    size = line.get("extensions", {}).get("mf:font", {}).get("size")
                    if (
                        isinstance(size, bool)
                        or not isinstance(size, (int, float))
                        or not math.isfinite(size)
                        or size <= 0
                    ):
                        size = None
                    metric = measure_word(pixels, word, size, scale)
                    measured_words += 1
                    measurements.append(metric)
                    font_sizes[str(metric["effective_font_size_px"])] += 1
                    punctuation = bool(word["text"]) and not any(c.isalnum() for c in word["text"])
                    hyphen = word.get("hyphenation")
                    record = {
                        "page_id": page_id,
                        "word_id": word_id,
                        "line_id": line["id"],
                        "text": word["text"],
                        "image_path": page["image"]["path"],
                        "columns": params["columns"],
                        "degradation": params["degradation"],
                        "angle_degrees": params["angle_degrees"],
                        "category": block["category"],
                        "punctuation_only": punctuation,
                        "hyphenation_part": hyphen["part"] if hyphen else None,
                        **metric,
                    }
                    if metric["reasons"]:
                        report["suspects"].append(record)
                    rank = (metric["contrast_gray_levels"], metric["ink_pixels"], word_id)
                    _candidate(candidates, "contrast", record, rank)
                    if sum(c.isalnum() for c in word["text"]) >= 2:
                        _candidate(candidates, "lexical", record, rank)
                    _candidate(
                        candidates, "font", record, (metric["effective_font_size_px"] or 0, *rank)
                    )
                    if punctuation:
                        _candidate(candidates, "punctuation", record, rank)
                    if hyphen:
                        _candidate(candidates, f"hyphen_{hyphen['part']}", record, rank)
                    if block["category"] in ("titre", "annonce"):
                        _candidate(
                            candidates,
                            "title" if block["category"] == "titre" else "advertisement",
                            record,
                            rank,
                        )
                except (ValueError, KeyError, TypeError, OverflowError) as exc:
                    report["errors"].append(f"{page_id}/{word_id}: {exc}")
            minima = {}
            for key in (
                "contrast_gray_levels",
                "ink_pixels",
                "font_size_px",
                "effective_font_size_px",
                "bbox_width_px",
                "bbox_height_px",
            ):
                values = [m[key] for m in measurements if m[key] is not None]
                minima[f"minimum_{key}"] = min(values) if values else None
            report["pages"].append(
                {
                    "page_id": page_id,
                    "columns": params["columns"],
                    "degradation": params["degradation"],
                    "angle_degrees": params["angle_degrees"],
                    "words_declared": word_count,
                    "words_measured": len(measurements),
                    "suspect_words": sum(bool(m["reasons"]) for m in measurements),
                    "effective_font_sizes_px": dict(sorted(font_sizes.items())),
                    **minima,
                }
            )
            candidates_by_page.append(candidates)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            OverflowError,
            Image.DecompressionBombError,
        ) as exc:
            report["errors"].append(f"{page_id}: {exc}")
    report["summary"] = {
        "pages_declared": len(records),
        "pages_audited": len(report["pages"]),
        "words_declared": total_words,
        "words_measured": measured_words,
        "suspect_words": len(report["suspects"]),
        "suspect_reasons": dict(
            sorted(
                Counter(reason for word in report["suspects"] for reason in word["reasons"]).items()
            )
        ),
    }
    for key in (
        "contrast_gray_levels",
        "ink_pixels",
        "font_size_px",
        "effective_font_size_px",
        "bbox_width_px",
        "bbox_height_px",
    ):
        values = [
            page[f"minimum_{key}"] for page in report["pages"] if page[f"minimum_{key}"] is not None
        ]
        report["summary"][f"minimum_{key}"] = min(values) if values else None
    samples = _choose_samples(candidates_by_page, max_samples)
    report["samples"] = samples
    report["summary"]["selected_words"] = len(samples)
    report["sample_strata"] = dict(
        sorted(Counter(f"{s['columns']} columns / {s['degradation']}" for s in samples).items())
    )
    if samples_dir is not None:
        report["sample_sheets"] = _write_samples(root, samples_dir, samples)
    report["status"] = "fail" if report["errors"] or report["suspects"] else "pass"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--samples-dir", type=Path)
    parser.add_argument("--max-samples", type=int, default=150)
    args = parser.parse_args(argv)
    try:
        result = audit_legibility(args.root, args.report, args.samples_dir, args.max_samples)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": str(args.report.resolve()),
                "summary": result["summary"],
                "errors": result["errors"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
