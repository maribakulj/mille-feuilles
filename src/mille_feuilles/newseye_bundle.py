"""Bounded, standalone PAGE NewsEye bundles; sources are never modified.

The independent reader is compared with an expectation derived from canonical
data and the published profile. No producer code builds that expectation.
Archived source validation is evidence of the export-time check, not a new
validation of absent source texts, fonts, rights or historical provenance.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import shutil

from lxml import etree as ET
from PIL import Image
from shapely.errors import ShapelyError
from shapely.geometry import Polygon

from .io import ROOT, sha256
from .pipeline import environment, git_state
from .validation import _finite_errors, _structural_errors, load_json, safe_path, validate_dataset, validate_page

FORMAT = "mille-feuilles-newseye-bundle"
PROFILE = "page-newseye-v1"
VERSION = "1"
PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
MAX_PAGES = 100
MAX_BYTES = 200_000_000
RESERVE_BYTES = 500_000_000
SCHEMA_FILES = {
    "page-2019-07-15.xsd": "5d7da5af5f5e06d3b9cd1e78b407ffca1862f78ad9823ed89c302fb6409932d5",
    "PAGE-LICENSE": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
    "provenance.json": "f2e8bb4dc146e90dd0aa39798f2081863ed5d258eeee14eaa875f5eb3ea5317c",
}
SCOPE = {
    "source_validation": "recorded pass at export",
    "source_rights_revalidated": False,
    "external_reader": "not_evaluated",
    "model_evaluation": "not_evaluated",
    "byte_budget": "preflight estimate and post-copy check; not an atomic quota",
}


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


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
    issues = list(_finite_errors(value))
    if issues:
        raise ValueError(issues[0])
    return value


def _reference(path: str, data: bytes) -> dict:
    return {"path": path, "sha256": _digest(data)}


def _identifier(value) -> str:
    if (not isinstance(value, str) or len(value) > 250
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", value) is None):
        raise ValueError(f"Unsafe canonical page identifier: {value!r}")
    return value


def _project(page: dict, image_filename: str):
    # Local import allows preflight refusals before loading the optional producer.
    from .exports_newseye import project_page

    return project_page(page, image_filename=image_filename)


def _read(xml: bytes) -> dict:
    from .newseye_reader import read_page

    return read_page(xml)


def _projection_environment() -> dict:
    value = deepcopy(environment())
    modules = {"newseye_bundle.py": sha256(Path(__file__))}
    for name in ("exports_newseye", "newseye_reader"):
        module = importlib.import_module(f"{__package__}.{name}")
        modules[f"{name}.py"] = sha256(Path(module.__file__))
    value["projection_modules"] = modules
    return value


def _source_snapshot(root: Path) -> dict:
    """Fingerprint files without following an unchecked path outside source."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        checked = safe_path(root, relative)
        if path.is_symlink() and (not checked.is_file()):
            raise ValueError(f"Source symlink must name a safe regular file: {relative}")
        if checked.is_file():
            result[relative] = {"sha256": sha256(checked), "size_bytes": checked.stat().st_size}
    return result


def _schema_bytes() -> dict[str, bytes]:
    result = {}
    for name, expected in SCHEMA_FILES.items():
        data = (ROOT / "schemas/xml" / name).read_bytes()
        if _digest(data) != expected:
            raise ValueError(f"Pinned PAGE schema provenance changed: {name}")
        result[f"schemas/{name}"] = data
    return result


def _xml_schema(data: bytes):
    if _digest(data) != SCHEMA_FILES["page-2019-07-15.xsd"]:
        raise ValueError("PAGE XSD differs from the pinned official schema")
    parser = ET.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    return ET.XMLSchema(ET.fromstring(data, parser))


def _rounded(points, image):
    # Independent implementation of SPEC §5; never call producer/export helpers.
    limits = [image["width"], image["height"]]
    return [[max(0, min(limits[axis], math.floor(value + 0.5)))
             for axis, value in enumerate(point)] for point in points]


def _expectation(page: dict, image_filename: str) -> tuple[dict, dict]:
    blocks = {b["id"]: b for b in page["blocks"]}
    lines = {line["id"]: line for line in page["lines"]}
    words = {word["id"]: word for word in page["words"]}
    reading = {"text_regions_in_order": [], "advert_cover_max": {}, "advert_ranks": [],
               "separators": [], "omitted_text_regions": []}
    geometry = {"regions": {}, "lines": {}, "words": {}}
    mapping, word_ids_by_line, region_types = {}, {}, {}
    types = {"titre": "heading", "legende": "caption", "texte": "paragraph",
             "annonce": "paragraph", "autre": "paragraph"}
    for index, bid in enumerate(page["reading_order"]["block_ids"]):
        block = blocks[bid]
        if block["category"] not in types or block["article_id"] is None:
            raise ValueError(f"Canonical block is not representable in {PROFILE}: {bid}")
        region_id = f"r_{bid}"
        kind = "texte" if block["category"] == "autre" else block["category"]
        region = {"id": region_id, "structure": types[block["category"]], "kind": kind, "lines": []}
        mapping[region_id] = bid
        region_types[region_id] = "TextRegion"
        geometry["regions"][region_id] = _rounded(block["polygon"], page["image"])
        advertisement = block["category"] == "annonce"
        reading["advert_cover_max"][region_id] = float(advertisement)
        if advertisement:
            advert_id = f"a_{bid}"
            mapping[advert_id] = bid
            region_types[advert_id] = "AdvertRegion"
            geometry["regions"][advert_id] = deepcopy(geometry["regions"][region_id])
            reading["advert_ranks"].append(index)
        for lid in block["line_ids"]:
            line, xml_lid = lines[lid], f"l_{lid}"
            mapping[xml_lid] = lid
            region["lines"].append([xml_lid, block["article_id"], line["text"]])
            geometry["lines"][xml_lid] = [_rounded(line["polygon"], page["image"]),
                                               _rounded(line["baseline"], page["image"])]
            word_ids_by_line[xml_lid] = [f"w_{wid}" for wid in line["word_ids"]]
            for wid in line["word_ids"]:
                word, xml_wid = words[wid], f"w_{wid}"
                mapping[xml_wid] = wid
                geometry["words"][xml_wid] = [word["text"], _rounded(word["polygon"], page["image"])]
        reading["text_regions_in_order"].append(region)
    for bid in page["reading_order"]["unordered_block_ids"]:
        block = blocks[bid]
        if block["category"] not in ("separateur", "illustration"):
            raise ValueError(f"Unsupported unordered canonical block: {bid}")
        prefix = "s" if block["category"] == "separateur" else "g"
        region_id = f"{prefix}_{bid}"
        mapping[region_id] = bid
        region_types[region_id] = "SeparatorRegion" if prefix == "s" else "GraphicRegion"
        geometry["regions"][region_id] = _rounded(block["polygon"], page["image"])
        if prefix == "s":
            reading["separators"].append(region_id)
    reading["separators"].sort()
    return {"reading": reading, "geometry": geometry, "word_ids_by_line": word_ids_by_line,
            "region_types": region_types,
            "image": {"filename": image_filename, "width": page["image"]["width"],
                      "height": page["image"]["height"]}}, mapping


def _projection_errors(xml: bytes, page: dict, image_filename: str, schema) -> tuple[list[str], dict]:
    errors = []
    parser = ET.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    root = ET.fromstring(xml, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError("DOCTYPE is forbidden in a NewsEye bundle")
    if root.get("pcGtsId") != f"p_{page['page_id']}":
        errors.append("XML page identifier differs from canonical")
    if not schema.validate(root):
        errors.extend(f"PAGE XSD: {entry.message}" for entry in schema.error_log)
    expected, mapping = _expectation(page, image_filename)
    regions = expected["geometry"]["regions"]
    polygons = {identity: Polygon(points) for identity, points in regions.items()}
    if any(not polygon.is_valid or polygon.area <= 0 for polygon in polygons.values()):
        raise ValueError("Canonical region polygon degenerates after integer rounding")
    for aid in regions:
        if not aid.startswith("a_"):
            continue
        advert = polygons[aid]
        for rid in regions:
            if rid.startswith("r_") and rid != "r_" + aid[2:]:
                if advert.intersection(polygons[rid]).area > 0:
                    errors.append(f"advert_overlap after canonical rounding: {aid}/{rid}")
    observed = _read(xml)
    if set(observed) != set(expected):
        errors.append("independent reader observation fields differ")
    for name in ("image", "geometry", "word_ids_by_line", "region_types"):
        if observed.get(name) != expected[name]:
            errors.append(f"independent {name} differs from canonical")
    actual_reading = observed.get("reading", {})
    expected_reading = expected["reading"]
    if set(actual_reading) != set(expected_reading):
        errors.append("independent reading fields differ")
    for key in expected_reading.keys() - {"advert_cover_max"}:
        if actual_reading.get(key) != expected_reading[key]:
            errors.append(f"independent reading.{key} differs from canonical")
    covers = actual_reading.get("advert_cover_max", {})
    if set(covers) != set(expected_reading["advert_cover_max"]) or any(
        not isinstance(covers.get(key), (int, float)) or isinstance(covers.get(key), bool)
        or not math.isfinite(covers[key]) or abs(covers[key] - value) > 1e-12
        for key, value in expected_reading["advert_cover_max"].items()
    ):
        errors.append("independent advert cover differs from canonical")
    return errors, mapping


def _report_errors(report: dict, page: dict, image_filename: str, mapping: dict) -> list[str]:
    errors = _structural_errors(report, "newseye-report")
    if errors:
        return errors
    expected = {"format": "mille-feuilles-newseye-report", "version": "2",
                "page_id": page["page_id"], "profile": PROFILE,
                "image_filename": image_filename, "id_mapping": mapping}
    return [f"page projection report {key} differs" for key, value in expected.items()
            if report[key] != value]


def _png_errors(path: Path, page: dict) -> list[str]:
    errors = []
    with Image.open(path) as image:
        if image.format != "PNG":
            errors.append("copied image is not PNG")
        if image.size != (page["image"]["width"], page["image"]["height"]):
            errors.append("copied PNG dimensions differ from canonical")
        if image.mode != page["image"]["color_mode"]:
            errors.append("copied PNG mode differs from canonical")
        image.verify()
    # verify() checks chunk CRCs but does not decode the compressed pixel stream.
    with Image.open(path) as image:
        image.load()
    if sha256(path) != page["image"]["sha256"]:
        errors.append("copied PNG hash differs from canonical")
    return errors


def _source_report_errors(value, source_manifest=None) -> list[str]:
    if not isinstance(value, dict) or value.get("status") != "pass" or value.get("errors") != []:
        return ["source validation is not a recorded pass"]
    checks = value.get("checks")
    if (not isinstance(checks, list) or not checks
            or any(not isinstance(item, dict) or item.get("status") != "pass" for item in checks)):
        return ["source validation has failed, missing or unevaluated checks"]
    names = [item.get("name") for item in checks]
    if (any(not isinstance(name, str) for name in names) or len(names) != len(set(names))
            or not {"exports", "export_inventory"} <= set(names)):
        return ["source validation omits unique completed export checks"]
    required = {"manifest", "file_hashes", "strict_json_files", "unique_manifest_entries",
                "manifest_coverage", "asset_registry", "partition_receipt", "assets"}
    if source_manifest is not None:
        required.update(f"{prefix}:{page['id']}" for page in source_manifest["pages"]
                        for prefix in ("page", "page_files"))
        extensions = source_manifest.get("extensions", {})
        if "mf:partition" in extensions:
            required.add("partition_characters")
        if "mf:import_report" in extensions:
            required.add("import_receipt")
        if source_manifest["profile"] in {"fr_press_19c_columns_4_6_measured", "fr_press_19c_layout_v2"}:
            required.add("degradation_profile")
        if source_manifest["profile"] == "fr_press_19c_layout_v2":
            required.add("layout_profile")
    missing = sorted(required - set(names))
    return ["source validation omits completed checks: " + ", ".join(missing)] if missing else []


def _select(manifest: dict, page_ids) -> list[tuple[int, dict]]:
    records = manifest["pages"]
    known = [_identifier(record["id"]) for record in records]
    if len(known) != len(set(known)):
        raise ValueError("Source manifest page identifiers are not unique")
    if page_ids is None:
        selected = known
    else:
        if not isinstance(page_ids, (list, tuple)) or not page_ids:
            raise ValueError("page_ids must be a nonempty list or tuple")
        selected = [_identifier(value) for value in page_ids]
        if len(selected) != len(set(selected)):
            raise ValueError("Selected page identifiers must be unique")
        if not set(selected) <= set(known):
            raise ValueError("Unknown selected page identifier")
    if not 1 <= len(selected) <= MAX_PAGES:
        raise ValueError(f"Bundle page budget requires 1..{MAX_PAGES} selected pages")
    if len({identity.casefold() for identity in selected}) != len(selected):
        raise ValueError("Selected identifiers collide on a case-insensitive filesystem")
    chosen = set(selected)
    return [(index, record) for index, record in enumerate(records) if record["id"] in chosen]


def _expected_artifacts(manifest: dict) -> dict:
    result = {}

    def add(reference, role):
        path = reference["path"]
        if path in result:
            raise ValueError(f"Duplicate bundle reference: {path}")
        result[path] = {"sha256": reference["sha256"], "role": role}

    add(manifest["source"]["manifest"], "source_manifest")
    add(manifest["source"]["validation"], "source_validation")
    add(manifest["generator"]["environment"], "environment")
    for key, role in (("xsd", "schema"), ("license", "schema_license"), ("provenance", "schema_provenance")):
        add(manifest["schema"][key], role)
    for page in manifest["pages"]:
        for key, role in (("xml", "xml"), ("image", "image"), ("canonical", "canonical"), ("report", "page_report")):
            add(page[key], role)
    if len({path.casefold() for path in result}) != len(result):
        raise ValueError("Bundle references collide on a case-insensitive filesystem")
    return result


def export_bundle(source_root: Path, output_root: Path, page_ids=None) -> dict:
    """Export to a new disjoint directory; preserve partial output on I/O failure.

    Selection, projection, independent checks and resource estimates all finish
    before mkdir. The byte budget is not an atomic filesystem quota.
    """
    try:
        source, output = Path(source_root).resolve(), Path(output_root).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Cannot resolve source/output paths: {exc}") from exc
    if not source.is_dir():
        raise ValueError("Source dataset directory is absent")
    requested = Path(output_root)
    if requested.exists() or requested.is_symlink() or output.exists():
        raise ValueError("Bundle destination must be new; no overwrite")
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Source dataset and output bundle must be disjoint")
    before = _source_snapshot(source)
    source_report = validate_dataset(source, verify_exports=True)
    if _source_report_errors(source_report):
        raise ValueError("Source dataset must pass complete validation including exports")
    manifest_path = safe_path(source, "manifest.json")
    source_manifest_bytes = manifest_path.read_bytes()
    source_manifest = _decoded(source_manifest_bytes)
    issues = _structural_errors(source_manifest, "manifest")
    if issues:
        raise ValueError("Invalid source manifest: " + "; ".join(issues[:5]))
    issues = _source_report_errors(source_report, source_manifest)
    if issues:
        raise ValueError("Incomplete source validation coverage: " + "; ".join(issues))
    selected = _select(source_manifest, page_ids)
    blobs = _schema_bytes()
    blobs["provenance/source-manifest.json"] = source_manifest_bytes
    blobs["provenance/source-validation.json"] = _encoded(source_report)
    schema = _xml_schema(blobs["schemas/page-2019-07-15.xsd"])
    projection_environment = _projection_environment()
    commit, dirty = git_state()
    pages, images = [], {}
    copied_bytes = sum(len(data) for data in blobs.values())
    for index, reference in selected:
        identity = reference["id"]
        canonical_source = safe_path(source, reference["path"])
        if copied_bytes + canonical_source.stat().st_size > MAX_BYTES:
            raise ValueError("Bundle byte budget exceeded before reading canonical page")
        canonical_bytes = canonical_source.read_bytes()
        if _digest(canonical_bytes) != reference["sha256"]:
            raise ValueError(f"Canonical source changed: {identity}")
        page = _decoded(canonical_bytes)
        issues = validate_page(page)
        if issues or page["page_id"] != identity:
            raise ValueError(f"Invalid selected canonical page: {identity}: {issues[:5]}")
        image_source = safe_path(source, page["image"]["path"])
        image_path = f"images/{identity}.png"
        if copied_bytes + len(canonical_bytes) + image_source.stat().st_size > MAX_BYTES:
            raise ValueError("Bundle byte budget exceeded before reading source image")
        issues = _png_errors(image_source, page)
        if issues:
            raise ValueError(f"Invalid selected source image: {identity}: {issues}")
        xml, projection_report = _project(page, image_path)
        issues, mapping = _projection_errors(xml, page, image_path, schema)
        issues.extend(_report_errors(projection_report, page, image_path, mapping))
        if issues:
            raise ValueError(f"Projection failed independent checks: {identity}: {issues[:8]}")
        xml_path, canonical_path, report_path = f"{identity}.xml", f"provenance/pages/{identity}.json", f"reports/{identity}.json"
        blobs[xml_path], blobs[canonical_path], blobs[report_path] = xml, canonical_bytes, _encoded(projection_report)
        images[image_path] = image_source
        pages.append({"id": identity, "source_index": index,
                      "xml": _reference(xml_path, xml), "canonical": _reference(canonical_path, canonical_bytes),
                      "report": _reference(report_path, blobs[report_path]),
                      "image": {"path": image_path, "sha256": page["image"]["sha256"],
                                "width": page["image"]["width"], "height": page["image"]["height"]}})
        copied_bytes += len(xml) + len(canonical_bytes) + len(blobs[report_path]) + image_source.stat().st_size
        if copied_bytes > MAX_BYTES:
            raise ValueError(f"Bundle byte budget exceeded before output creation: {copied_bytes}")
    blobs["provenance/environment.json"] = _encoded(projection_environment)
    manifest = {
        "format": FORMAT, "version": VERSION, "profile": PROFILE,
        "source": {"dataset_id": source_manifest["dataset_id"],
                   "manifest": _reference("provenance/source-manifest.json", source_manifest_bytes),
                   "validation": _reference("provenance/source-validation.json", blobs["provenance/source-validation.json"])},
        "generator": {"commit": commit, "dirty": dirty,
                      "environment": _reference("provenance/environment.json", blobs["provenance/environment.json"])},
        "schema": {"name": "PAGE 2019-07-15", "namespace": PAGE_NS,
                   "xsd": _reference("schemas/page-2019-07-15.xsd", blobs["schemas/page-2019-07-15.xsd"]),
                   "license": _reference("schemas/PAGE-LICENSE", blobs["schemas/PAGE-LICENSE"]),
                   "provenance": _reference("schemas/provenance.json", blobs["schemas/provenance.json"])},
        "page_ids": [page["id"] for page in pages], "pages": pages, "artifacts": [], "scope": deepcopy(SCOPE),
    }
    expected = _expected_artifacts(manifest)
    for path, reference in sorted(expected.items()):
        size = len(blobs[path]) if path in blobs else images[path].stat().st_size
        manifest["artifacts"].append({"path": path, **reference, "size_bytes": size})
    issues = _structural_errors(manifest, "newseye-manifest")
    if issues:
        raise ValueError("Invalid bundle manifest before output creation: " + "; ".join(issues[:5]))
    blobs["manifest.json"] = _encoded(manifest)
    estimated = sum(len(data) for data in blobs.values()) + sum(path.stat().st_size for path in images.values())
    if estimated > MAX_BYTES:
        raise ValueError(f"Bundle byte budget exceeded before output creation: {estimated}")
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    free = shutil.disk_usage(ancestor).free
    if free < estimated + RESERVE_BYTES:
        raise ValueError(f"Insufficient space before output creation: {free}; {estimated + RESERVE_BYTES} required")
    if _source_snapshot(source) != before:
        raise ValueError("Source changed during preflight; no output created")
    if git_state() != (commit, dirty) or _projection_environment() != projection_environment:
        raise ValueError("Projection code/environment changed during preflight; no output created")
    output.mkdir(parents=True, exist_ok=False)
    for relative, data in sorted(blobs.items()):
        if relative == "manifest.json":
            continue
        destination = safe_path(output, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)
    for relative, original in sorted(images.items()):
        destination = safe_path(output, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with original.open("rb") as reader, destination.open("xb") as writer:
            copied = 0
            allowed = next(a["size_bytes"] for a in manifest["artifacts"] if a["path"] == relative)
            while chunk := reader.read(1024 * 1024):
                copied += len(chunk)
                if copied > allowed:
                    raise ValueError("Source image grew during export; partial output preserved")
                writer.write(chunk)
    if _source_snapshot(source) != before:
        raise ValueError("Source changed during export; partial output preserved")
    # A new output under an unignored repository directory can itself change
    # git's dirty flag. Compare the commit and exact code/environment instead.
    if git_state()[0] != commit or _projection_environment() != projection_environment:
        raise ValueError("Projection code/environment changed; partial output preserved")
    with (output / "manifest.json").open("xb") as stream:
        stream.write(blobs["manifest.json"])
    report = validate_bundle(output)
    report["source_unchanged"] = True
    report["budget"] = {"max_pages": MAX_PAGES, "max_bytes": MAX_BYTES, "estimated_bytes": estimated,
                        "reserve_bytes": RESERVE_BYTES, "available_bytes": free,
                        "enforcement": SCOPE["byte_budget"]}
    return report


def validate_bundle(root: Path) -> dict:
    """Read a standalone bundle without opening source texts, fonts or datasets."""
    report = {"format": "mille-feuilles-newseye-bundle-validation", "version": VERSION,
              "status": "fail", "errors": [], "checks": [], "scope": deepcopy(SCOPE), "pages": 0}

    def check(name, errors):
        report["checks"].append({"name": name, "status": "fail" if errors else "pass", "errors": errors})
        report["errors"].extend(f"{name}: {error}" for error in errors)

    try:
        root = Path(root).resolve()
        if not root.is_dir():
            raise ValueError("Bundle directory is absent")
        actual, directories, total = {}, set(), 0
        for path in root.rglob("*"):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ValueError(f"Symlink is forbidden in a standalone bundle: {relative}")
            checked = safe_path(root, relative)
            if checked.is_dir():
                directories.add(relative)
            elif checked.is_file():
                actual[relative] = checked.stat().st_size
                total += actual[relative]
                if total > MAX_BYTES or len(actual) > 4 * MAX_PAGES + 7:
                    raise ValueError("Bundle exceeds the validation resource budget")
            else:
                raise ValueError(f"Unsupported bundle filesystem entry: {relative}")
        manifest = load_json(safe_path(root, "manifest.json"))
        issues = _structural_errors(manifest, "newseye-manifest")
        check("manifest", issues)
        if issues:
            return report
        expected = _expected_artifacts(manifest)
        artifacts = {artifact["path"]: artifact for artifact in manifest["artifacts"]}
        issues = []
        if len(artifacts) != len(manifest["artifacts"]):
            issues.append("duplicate artifact path")
        if set(artifacts) != set(expected) or set(actual) != set(expected) | {"manifest.json"}:
            issues.append("artifact inventory is not exact")
        allowed_dirs = {str(parent) for relative in expected for parent in Path(relative).parents if str(parent) != "."}
        if directories != allowed_dirs:
            issues.append("unexpected or missing bundle directories")
        for relative in expected:
            if relative not in artifacts or relative not in actual:
                continue
            artifact, reference = artifacts[relative], expected[relative]
            path = safe_path(root, relative)
            if artifact["role"] != reference["role"] or artifact["sha256"] != reference["sha256"]:
                issues.append(f"artifact reference differs: {relative}")
            if artifact["size_bytes"] != actual[relative] or sha256(path) != reference["sha256"]:
                issues.append(f"artifact size/hash differs: {relative}")
        check("inventory", issues)
        if issues:
            return report
        source_manifest = load_json(safe_path(root, manifest["source"]["manifest"]["path"]))
        source_validation = load_json(safe_path(root, manifest["source"]["validation"]["path"]))
        issues = _structural_errors(source_manifest, "manifest")
        check("source_manifest_structure_only", issues)
        if issues:
            return report
        issues = []
        if source_manifest.get("dataset_id") != manifest["source"]["dataset_id"]:
            issues.append("source dataset identifier differs")
        issues.extend(_source_report_errors(source_validation, source_manifest))
        check("source_validation_record_only", issues)
        recorded_environment = load_json(safe_path(root, manifest["generator"]["environment"]["path"]))
        modules = recorded_environment.get("projection_modules", {}) if isinstance(recorded_environment, dict) else {}
        module_names = {"newseye_bundle.py", "exports_newseye.py", "newseye_reader.py"}
        environment_issues = []
        if (not isinstance(modules, dict) or set(modules) != module_names
                or any(not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None
                       for value in modules.values())):
            environment_issues.append("projection environment omits exact module hash records")
        check("projection_environment_record_only", environment_issues)
        schema_issues = []
        for name, digest in SCHEMA_FILES.items():
            if sha256(root / "schemas" / name) != digest:
                schema_issues.append(f"pinned schema provenance differs: {name}")
        check("pinned_offline_schema", schema_issues)
        if schema_issues:
            return report
        schema = _xml_schema((root / "schemas/page-2019-07-15.xsd").read_bytes())
        source_records = source_manifest["pages"]
        known = [entry["id"] for entry in source_records]
        selected = manifest["page_ids"]
        issues = []
        if len(known) != len(set(known)) or selected != [identity for identity in known if identity in set(selected)]:
            issues.append("selection is unknown, duplicated or not in source manifest order")
        if selected != [entry["id"] for entry in manifest["pages"]]:
            issues.append("page records differ from selected identifiers")
        check("selection", issues)
        if issues:
            return report
        for entry in manifest["pages"]:
            identity = entry["id"]
            issues = []
            paths = {"xml": f"{identity}.xml", "image": f"images/{identity}.png",
                     "canonical": f"provenance/pages/{identity}.json", "report": f"reports/{identity}.json"}
            for key, relative in paths.items():
                if entry[key]["path"] != relative:
                    issues.append(f"noncanonical bundle {key} path")
            if entry["source_index"] != known.index(identity):
                issues.append("source page index differs")
            source_reference = source_records[known.index(identity)]
            if source_reference["sha256"] != entry["canonical"]["sha256"]:
                issues.append("canonical bytes differ from archived source manifest")
            page = load_json(safe_path(root, entry["canonical"]["path"]))
            issues.extend(validate_page(page))
            if page["page_id"] != identity:
                issues.append("canonical page identifier differs")
            if {key: entry["image"][key] for key in ("sha256", "width", "height")} != {
                key: page["image"][key] for key in ("sha256", "width", "height")
            }:
                issues.append("image reference differs from canonical")
            issues.extend(_png_errors(safe_path(root, entry["image"]["path"]), page))
            observed_errors, mapping = _projection_errors(
                safe_path(root, entry["xml"]["path"]).read_bytes(), page, paths["image"], schema,
            )
            issues.extend(observed_errors)
            projection_report = load_json(safe_path(root, entry["report"]["path"]))
            issues.extend(_report_errors(projection_report, page, paths["image"], mapping))
            check(f"page:{identity}", issues)
            report["pages"] += 1
        report["written_bytes"] = total
        report["status"] = "fail" if report["errors"] else "pass"
    except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError, ET.LxmlError,
            Image.DecompressionBombError, ShapelyError) as exc:
        check("bundle", [f"{type(exc).__name__}: {exc}"])
    return report
