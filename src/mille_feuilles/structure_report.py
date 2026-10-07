"""Bounded descriptive reports from selected canonical pages; no corpus or image I/O.

This orchestration does not validate a complete source dataset. Source images,
exports, assets, rights and text content are deliberately not opened. Only the
selected canonical bytes are checked against the native manifest. Statistical
positions never constitute an acceptance criterion for document realism.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import shutil
import sys

from . import io as io_module
from . import realism
from . import validation
from .io import ROOT, sha256
from .pipeline import git_state
from .validation import _finite_errors, _structural_errors, safe_path, validate_page

MAX_PAGES = 100
MAX_CANONICAL_BYTES = 200_000_000
MAX_OUTPUT_BYTES = 20_000_000
RESERVE_BYTES = 500_000_000
CALIBRER_PATH = ROOT / "tools/cadrage/calibrer.py"
CALIBRATION_PATH = ROOT / "tools/cadrage/sortie/calibration.json"
SCOPE = {
    "canonical_only": True,
    "source_dataset_validation": "not_performed",
    "source_images_assets_exports_rights": "not_checked",
    "source_text_provenance": "not_revalidated",
    "real_corpus_access": "not_performed",
    "reference_exclusions": "not_revalidated",
    "physical_units": "not_measured_dpi_none",
    "realism_verdict": "not_evaluated",
    "recalculation_from_canonical": "requires selected source files with recorded hashes",
    "limits": {"max_pages": MAX_PAGES, "max_canonical_bytes": MAX_CANONICAL_BYTES,
               "max_output_bytes": MAX_OUTPUT_BYTES, "reserve_bytes": RESERVE_BYTES},
}


def _encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decoded(data: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique)
    errors = list(_finite_errors(value))
    if errors:
        raise ValueError(errors[0])
    return value


def _read_bounded(path: Path, limit: int) -> bytes:
    if limit < 0 or path.stat().st_size > limit:
        raise ValueError(f"Input byte budget exceeded: {path.name}")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Input grew beyond byte budget: {path.name}")
    return data


def _reference(relative: str, data: bytes) -> dict:
    return {"path": relative, "sha256": _digest(data), "size_bytes": len(data)}


def _environment() -> dict:
    modules = {"realism.py": Path(realism.__file__), "structure_report.py": Path(__file__),
               "validation.py": Path(validation.__file__), "io.py": Path(io_module.__file__)}
    return {"python": sys.version,
            "packages": {name: importlib.metadata.version(name)
                         for name in ("Pillow", "numpy", "fonttools", "lxml", "jsonschema", "shapely")},
            "modules": {name: sha256(path) for name, path in modules.items()},
            "schemas": {name: sha256(ROOT / "schemas" / name)
                        for name in ("manifest.schema.json", "page.schema.json", "structure-report.schema.json")}}


def _selection(manifest: dict, page_ids, all_pages: bool) -> list[tuple[int, dict]]:
    if not isinstance(all_pages, bool) or (page_ids is None) == (not all_pages):
        raise ValueError("Choose explicitly page_ids or all_pages=True, exclusively")
    records = manifest["pages"]
    ids = [record["id"] for record in records]
    paths = [record["path"] for record in records]
    if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
        raise ValueError("Native manifest page IDs and paths must be unique")
    if all_pages:
        chosen = ids
    else:
        if not isinstance(page_ids, (list, tuple)) or not page_ids:
            raise ValueError("page_ids must be a nonempty explicit list")
        chosen = list(page_ids)
        if any(not isinstance(value, str) for value in chosen):
            raise ValueError("Page identifiers must be strings")
        if len(chosen) != len(set(chosen)) or not set(chosen) <= set(ids):
            raise ValueError("Selected page IDs must be unique and known")
    if not 1 <= len(chosen) <= MAX_PAGES:
        raise ValueError(f"Selected page budget requires 1..{MAX_PAGES} pages")
    if (any(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", value) is None for value in chosen)
            or len({value.casefold() for value in chosen}) != len(chosen)):
        raise ValueError("Selected IDs must be portable without case collisions")
    return [(index, record) for index, record in enumerate(records) if record["id"] in set(chosen)]


def _number(value, label, *, integer=False, positive=False):
    if value is None:
        return None
    try:
        finite = math.isfinite(value)
    except (TypeError, OverflowError):
        finite = False
    if (isinstance(value, bool) or not isinstance(value, int if integer else (int, float))
            or not finite or (positive and value <= 0)):
        raise ValueError(f"Invalid declared metadata: {label}")
    return value


def _page_metadata(page: dict, index: int, reference: dict) -> dict:
    params = page["provenance"]["parameters"]
    extensions = page["provenance"].get("extensions", {})
    templates = extensions.get("mf:template_article_ids")
    if "mf:template_article_ids" in extensions:
        known = {article["id"] for article in page["articles"]}
        if (not isinstance(templates, list) or any(not isinstance(value, str) for value in templates)
                or len(templates) != len(set(templates)) or not set(templates) <= known):
            raise ValueError("Invalid template article identification metadata")
    layout_columns = None
    if "layout" in params:
        layout = params["layout"]
        if not isinstance(layout, dict) or not isinstance(layout.get("zones"), list):
            raise ValueError("Invalid declared layout metadata")
        layout_columns = {}
        for zone in layout["zones"]:
            if (not isinstance(zone, dict) or not isinstance(zone.get("id"), str)
                    or not isinstance(zone.get("columns"), list) or not zone["columns"]
                    or zone["id"] in layout_columns):
                raise ValueError("Invalid declared zone metadata")
            layout_columns[zone["id"]] = len(zone["columns"])
    partition = params.get("partition")
    if partition is not None and (not isinstance(partition, str) or not partition):
        raise ValueError("Invalid declared partition metadata")
    return {"id": page["page_id"], "source_index": index, "canonical": reference,
            "schema_version": page["schema_version"], "profile": page["profile"],
            "width": page["image"]["width"], "height": page["image"]["height"],
            "declared_dpi": page["image"]["dpi"],
            "columns_declared": _number(params.get("columns"), "columns", integer=True, positive=True),
            "layout_columns_declared": layout_columns,
            "oversampling": _number(params.get("oversampling"), "oversampling", integer=True, positive=True),
            "angle_degrees": _number(params.get("angle_degrees"), "angle_degrees"),
            "partition": partition, "template_article_ids": templates}


def _variant(parts: list[dict], rows: list[dict], reference: dict, engine, *, include: bool) -> dict:
    merged = realism.merge_measures(parts)
    stats = realism.aggregate(merged, engine)
    excluded = merged["excluded"]
    return {"role": "primary" if include else "sensitivity",
            "cohort_status": "ND" if excluded else "complete",
            "cohort_reason": "template identification unavailable for part of the selected cohort" if excluded else None,
            "per_page": rows, "excluded": excluded,
            "stats": None if excluded else stats, "partial_stats": stats if excluded else None,
            "comparison": None if excluded else realism.compare(stats, reference["stats"], has_autre=merged["has_autre"])}


def build_report(source_root: Path, output_root: Path, *, page_ids: list[str] | None = None,
                 all_pages: bool = False, reference: str = "as:XIXe") -> dict:
    """Write two files in a new disjoint directory; keep partial output on failure.

    Canonical pages are loaded and released one at a time. Only raw observations,
    tiny source metadata and source fingerprints persist between pages.
    """
    source, output = Path(source_root).resolve(), Path(output_root).resolve()
    requested = Path(output_root)
    if not source.is_dir():
        raise ValueError("Native source directory is absent")
    if requested.exists() or requested.is_symlink() or output.exists():
        raise ValueError("Report destination must be new")
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Source and report destination must be disjoint")
    manifest_path = safe_path(source, "manifest.json")
    manifest_bytes = _read_bounded(manifest_path, MAX_OUTPUT_BYTES)
    manifest = _decoded(manifest_bytes)
    errors = _structural_errors(manifest, "manifest")
    if errors:
        raise ValueError("Invalid native manifest: " + "; ".join(errors[:5]))
    chosen = _selection(manifest, page_ids, all_pages)
    source_fingerprints = {"manifest.json": _reference("manifest.json", manifest_bytes)}
    canonical_bytes_total = 0
    for _, record in chosen:
        identity, relative = record["id"], record["path"]
        if relative != f"pages/{identity}.json":
            raise ValueError("Canonical page path must agree with its native identifier")
        canonical_bytes_total += safe_path(source, relative).stat().st_size
    if canonical_bytes_total > MAX_CANONICAL_BYTES:
        raise ValueError("Selected canonical byte budget exceeded")
    inputs = {}
    for key, path, expected in (("calibrer", CALIBRER_PATH, realism.CALIBRER_SHA256),
                                ("calibration", CALIBRATION_PATH, realism.CALIBRATION_SHA256)):
        data = _read_bounded(path, MAX_OUTPUT_BYTES)
        if _digest(data) != expected:
            raise ValueError(f"Pinned {key} SHA differs")
        inputs[key] = _reference(f"tools/cadrage/{'calibrer.py' if key == 'calibrer' else 'sortie/calibration.json'}", data)
    generation_environment, (commit, dirty) = _environment(), git_state()
    engine = realism.load_engine(CALIBRER_PATH)
    real_reference = realism.load_reference(CALIBRATION_PATH, reference)
    pages, parts, rows = [], {True: [], False: []}, {True: [], False: []}
    consumed = 0
    for index, record in chosen:
        data = _read_bounded(safe_path(source, record["path"]), MAX_CANONICAL_BYTES - consumed)
        consumed += len(data)
        if _digest(data) != record["sha256"]:
            raise ValueError(f"Canonical SHA differs: {record['id']}")
        page = _decoded(data)
        issues = validate_page(page)
        if issues:
            raise ValueError(f"Invalid canonical page {record['id']}: {'; '.join(issues[:5])}")
        if (page["page_id"] != record["id"] or page["profile"] != manifest["profile"]
                or page["schema_version"] != manifest["schema_version"]
                or page["image"]["path"] != f"images/{record['id']}.png"):
            raise ValueError("Canonical identifier, paths, profile or schema differs from native manifest")
        source_fingerprints[record["path"]] = _reference(record["path"], data)
        metadata = _page_metadata(page, index, source_fingerprints[record["path"]])
        pages.append(metadata)
        for include in (True, False):
            part = realism.measure_pages([page], engine, include_template=include)
            parts[include].append(part)
            if part["excluded"]:
                continue
            removed_articles = [] if include else metadata["template_article_ids"]
            rows[include].append({"page_id": page["page_id"], "values": part["values"],
                                  "counts": part["counts"], "has_autre": part["has_autre"],
                                  "removed_article_ids": removed_articles,
                                  "removed_block_ids": [block["id"] for block in page["blocks"]
                                                        if block["article_id"] in removed_articles]})
        # No canonical dictionaries or source text survive into the next iteration.
        del page, data
    report = {"format": "mille-feuilles-structural-report", "version": "1",
              "method": "cadrage-calibrer-a1-v1", "scope": deepcopy(SCOPE),
              "generator": {"commit": commit, "dirty": dirty, "environment": generation_environment},
              "inputs": {"source": {"dataset_id": manifest["dataset_id"],
                                    "schema_version": manifest["schema_version"], "profile": manifest["profile"],
                                    "manifest": source_fingerprints["manifest.json"], "total_pages": len(manifest["pages"])},
                         **inputs}, "reference": real_reference,
              "selection": {"mode": "all" if all_pages else "explicit", "page_ids": [p["id"] for p in pages], "pages": pages},
              "variants": {name: _variant(parts[include], rows[include], real_reference, engine, include=include)
                           for name, include in (("avec_gabarit", True), ("sans_gabarit", False))}}
    errors = _structural_errors(report, "structure-report")
    if errors:
        raise ValueError("Invalid structural report: " + "; ".join(errors[:5]))
    report_bytes = _encoded(report)
    digest = _digest(report_bytes)
    digest_bytes = f"{digest}  report.json\n".encode("ascii")
    output_bytes = len(report_bytes) + len(digest_bytes)
    if output_bytes > MAX_OUTPUT_BYTES:
        raise ValueError("Structural report output byte budget exceeded")
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < output_bytes + RESERVE_BYTES:
        raise ValueError("Insufficient free space for report and required reserve")

    def unchanged():
        for relative, original in source_fingerprints.items():
            path = safe_path(source, relative)
            if path.stat().st_size != original["size_bytes"] or sha256(path) != original["sha256"]:
                raise ValueError(f"Selected source changed: {relative}")
        if (sha256(CALIBRER_PATH) != inputs["calibrer"]["sha256"]
                or sha256(CALIBRATION_PATH) != inputs["calibration"]["sha256"]
                or git_state()[0] != commit or _environment() != generation_environment):
            raise ValueError("Measurement code or pinned reference changed")
    unchanged()
    if git_state()[1] != dirty:
        raise ValueError("Repository state changed during report preflight")
    output.mkdir(parents=True, exist_ok=False)
    for name, content in (("report.json", report_bytes), ("report.sha256", digest_bytes)):
        with (output / name).open("xb") as stream:
            stream.write(content)
    if (sha256(output / "report.json") != digest
            or (output / "report.sha256").read_bytes() != digest_bytes):
        raise ValueError("Report bytes changed during output")
    unchanged()
    return {"status": "pass", "errors": [],
            "checks": [{"name": name, "status": "pass"} for name in
                       ("selected_canonicals", "pinned_measurement", "report_schema", "source_stability", "output_hash")],
            "report_path": str(output / "report.json"), "report_sha256": digest,
            "selected_page_ids": report["selection"]["page_ids"]}
