#!/usr/bin/env python3
"""Accept the NewsEye CLI against frozen original canonical lots, without rendering.

Run only after integration on a clean committed revision. This script never calls
an exporter to construct its expected observations. Output and failure evidence
are preserved. Resource limits are checks between commands, not an atomic quota.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import resource
import shutil
import stat
import subprocess
import sys
import time

from jsonschema import Draft202012Validator
from lxml import etree

from mille_feuilles.io import ROOT
from mille_feuilles.newseye_reader import read_page
from mille_feuilles.pipeline import environment

MIN_FREE = 1_000_000_000
MAX_BYTES = 200_000_000
LEGACY_PAGE = "mf_0003"
SOURCE_ARCHIVES = {
    "legacy": "docs/reports/pilot-manifest.json",
    "layout": "docs/reports/lot4/acceptance/lots/compact-identity-x2/manifest.json",
}
PROJECTION_MODULES = ("newseye_bundle.py", "exports_newseye.py", "newseye_reader.py")
BUNDLE_CHECKS = {
    "manifest", "inventory", "source_manifest_structure_only", "source_validation_record_only",
    "projection_environment_record_only", "pinned_offline_schema", "selection",
}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def snapshot(root):
    """Include empty directories, so an accidentally created destination is visible."""
    result = {}
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        relative = path.relative_to(root).as_posix()
        if stat.S_ISREG(mode):
            result[relative] = {"kind": "file", "sha256": digest(path),
                                "size_bytes": path.stat().st_size}
        elif stat.S_ISDIR(mode):
            result[relative] = {"kind": "directory"}
        else:
            raise ValueError(f"Snapshot requires ordinary files/directories: {path}")
    return result


def safe_file(root, relative):
    if not isinstance(relative, str):
        raise ValueError("Expected a relative path string")
    posix = PurePosixPath(relative)
    if (not relative or posix.is_absolute() or "\\" in relative or ":" in relative
            or any(part in {"", ".", ".."} for part in relative.split("/"))
            or any(ord(char) < 32 or ord(char) == 127 for char in relative)):
        raise ValueError(f"Unsafe relative path: {relative!r}")
    path = root.joinpath(*posix.parts)
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing or escaping file: {relative!r}")
    if any(part.is_symlink() for part in [path, *path.parents] if part != root.parent):
        raise ValueError(f"Symlink in file reference: {relative!r}")
    return path


def volume(root):
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def existing_ancestor(path):
    while not path.exists():
        path = path.parent
    return path


def source_state():
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    return {"commit": commit, "dirty": dirty, "environment": environment(),
            "acceptance_script_sha256": digest(Path(__file__).resolve()),
            "python_executable": str(Path(sys.executable).resolve())}


def anchor_source(name, root, commit):
    """Bind input manifest bytes to the historical archive tracked at HEAD."""
    relative = SOURCE_ARCHIVES[name]
    committed = subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=ROOT)
    expected_sha256 = hashlib.sha256(committed).hexdigest()
    if digest(ROOT / relative) != expected_sha256:
        raise ValueError(f"{name}: historical archive differs from its committed Git blob")
    if digest(root / "manifest.json") != expected_sha256:
        raise ValueError(f"{name}: source manifest differs from committed historical archive {relative}")
    return {"archive": relative, "archive_commit": commit, "manifest_sha256": expected_sha256}


def canonical_observation(page):
    """Expected fields from SPEC sections 3--5 and the canonical page alone.

    The profile's advert has the same polygon as its TextRegion and may not
    overlap any other TextRegion. Its expected coverage is therefore 1, all
    other expected coverages are 0; no producer geometry helper is used here.
    """
    width, height = page["image"]["width"], page["image"]["height"]

    def points(values):
        # Written from section 5: floor(v + 0.5), then clamp each axis.
        return [[max(0, min(width, math.floor(x + 0.5))),
                 max(0, min(height, math.floor(y + 0.5)))] for x, y in values]

    blocks = {block["id"]: block for block in page["blocks"]}
    lines = {line["id"]: line for line in page["lines"]}
    words = {word["id"]: word for word in page["words"]}
    geometry = {"regions": {}, "lines": {}, "words": {}}
    reading = {"text_regions_in_order": [], "advert_cover_max": {}, "advert_ranks": [],
               "separators": [], "omitted_text_regions": []}
    word_ids_by_line, region_types, ordered_lines = {}, {}, []
    for rank, block_id in enumerate(page["reading_order"]["block_ids"]):
        block = blocks[block_id]
        category = block["category"]
        if category not in {"titre", "texte", "legende", "annonce", "autre"}:
            raise ValueError(f"Unsupported ordered canonical category: {category}")
        if not block["article_id"]:
            raise ValueError(f"Canonical text block has no article: {block_id}")
        region_id = f"r_{block_id}"
        geometry["regions"][region_id] = points(block["polygon"])
        region_types[region_id] = "TextRegion"
        reading["advert_cover_max"][region_id] = 1.0 if category == "annonce" else 0.0
        observed_lines = []
        for line_id in block["line_ids"]:
            line = lines[line_id]
            ordered_lines.append(line_id)
            xml_line_id = f"l_{line_id}"
            observed_lines.append([xml_line_id, block["article_id"], line["text"]])
            geometry["lines"][xml_line_id] = [points(line["polygon"]), points(line["baseline"])]
            word_ids_by_line[xml_line_id] = [f"w_{word_id}" for word_id in line["word_ids"]]
            for word_id in line["word_ids"]:
                word = words[word_id]
                geometry["words"][f"w_{word_id}"] = [word["text"], points(word["polygon"])]
        reading["text_regions_in_order"].append({
            "id": region_id, "structure": {"titre": "heading", "legende": "caption"}.get(
                category, "paragraph"),
            "kind": "texte" if category == "autre" else category, "lines": observed_lines,
        })
        if category == "annonce":
            advert_id = f"a_{block_id}"
            geometry["regions"][advert_id] = points(block["polygon"])
            region_types[advert_id] = "AdvertRegion"
            reading["advert_ranks"].append(rank)
    for block_id in page["reading_order"]["unordered_block_ids"]:
        block = blocks[block_id]
        if block["category"] == "separateur":
            region_id, region_type = f"s_{block_id}", "SeparatorRegion"
            reading["separators"].append(region_id)
        elif block["category"] == "illustration":
            region_id, region_type = f"g_{block_id}", "GraphicRegion"
        else:
            raise ValueError(f"Unsupported unordered canonical block: {block_id}")
        geometry["regions"][region_id] = points(block["polygon"])
        region_types[region_id] = region_type
    reading["separators"].sort()
    if ordered_lines != page["reading_order"]["line_ids"]:
        raise ValueError("Canonical block and global line orders disagree")
    if set(geometry["lines"]) != {f"l_{identifier}" for identifier in lines}:
        raise ValueError("Canonical line observation is incomplete")
    if set(geometry["words"]) != {f"w_{identifier}" for identifier in words}:
        raise ValueError("Canonical word observation is incomplete")
    return {"reading": reading, "image": {"filename": f"images/{page['page_id']}.png",
            "width": width, "height": height}, "geometry": geometry,
            "word_ids_by_line": word_ids_by_line, "region_types": region_types}


class Acceptance:
    def __init__(self, output, state, inputs):
        self.root, self.state, self.inputs = output, state, inputs
        self.manifests = {name: load_json(item["root"] / "manifest.json")
                          for name, item in inputs.items()}
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
        self.xsd = etree.XMLSchema(etree.parse(str(ROOT / "schemas/xml/page-2019-07-15.xsd"), parser))
        self.manifest_schema = Draft202012Validator(load_json(ROOT / "schemas/newseye-manifest.schema.json"))
        self.page_report_schema = Draft202012Validator(load_json(ROOT / "schemas/newseye-report.schema.json"))
        self.projection_environment = {
            **state["environment"],
            "projection_modules": {name: digest(ROOT / "src/mille_feuilles" / name)
                                   for name in PROJECTION_MODULES},
        }
        self.report = {
            "format": "mille-feuilles-newseye-acceptance", "version": "1", "status": "fail",
            "started_at_utc": datetime.now(timezone.utc).isoformat(), "source": state,
            "inputs": {name: {"path": str(item["root"]), "snapshot": item["snapshot"],
                              "historical_anchor": item["anchor"]}
                       for name, item in inputs.items()},
            "checks": [], "commands": [], "bundles": {}, "errors": [],
            "scope": "Original Mille Feuilles demonstration lots; no external corpus or model evaluation",
            "external_reader": "not_evaluated", "model_evaluation": "not_evaluated",
            "visual_review": {"status": "not_run", "note":
                "No new image rendering. Byte-identical raw PNG copies are checked; no visual review is claimed."},
            "resource_note": "At least 1 GB free and less than 200 MB output between commands; not an atomic quota",
        }

    def check(self, condition, description):
        if not condition:
            raise ValueError(description)
        self.report["checks"].append(description)

    def guard(self):
        self.check(source_state() == self.state, "Clean commit, code, script and environment unchanged")
        for name, item in self.inputs.items():
            self.check(snapshot(item["root"]) == item["snapshot"], f"{name}: complete source unchanged")
        free = shutil.disk_usage(self.root).free
        self.check(free >= MIN_FREE, f"Free output space {free} >= {MIN_FREE} bytes")
        size = volume(self.root)
        self.check(size < MAX_BYTES, f"Output volume {size} < {MAX_BYTES} bytes between commands")

    def run(self, name, arguments, *, failure=False, selected=None):
        self.guard()
        command = [sys.executable, "-m", "mille_feuilles.cli", *map(str, arguments)]
        out_path, err_path = self.root / f"logs/{name}.json", self.root / f"logs/{name}.stderr.log"
        out_path.parent.mkdir(exist_ok=True)
        entry = {"name": name, "argv": command, "cwd": str(ROOT),
                 "stdout": out_path.relative_to(self.root).as_posix(),
                 "stderr": err_path.relative_to(self.root).as_posix()}
        self.report["commands"].append(entry)
        print(f"Acceptation NewsEye : {name}", file=sys.stderr, flush=True)
        started = time.perf_counter()
        with out_path.open("xb") as out, err_path.open("xb") as err:
            result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, check=False)
        entry.update(exit_code=result.returncode, elapsed_seconds=time.perf_counter() - started)
        self.guard()
        self.check(result.returncode == (2 if failure else 0), f"{name}: expected CLI exit code")
        if failure:
            self.check(out_path.stat().st_size == 0, f"{name}: no success JSON emitted")
            return None
        result = load_json(out_path)
        self.check(result.get("status") == "pass", f"{name}: CLI report passed")
        checks = result.get("checks", [])
        names = [check.get("name") for check in checks]
        page_checks = {f"page:{page_id}" for page_id in selected or []}
        required = BUNDLE_CHECKS | page_checks
        self.check(selected is not None and len(names) == len(set(names))
                   and required <= set(names)
                   and {check for check in names if isinstance(check, str) and check.startswith("page:")}
                   == page_checks,
                   f"{name}: unique required bundle checks and exact selected page coverage")
        self.check(all(check.get("status") == "pass" for check in checks),
                   f"{name}: every reported check passed")
        return result

    def reference(self, bundle, record):
        path = safe_file(bundle, record["path"])
        self.check(digest(path) == record["sha256"], f"{bundle.name}: SHA-256 {record['path']}")
        return path

    def inspect_bundle(self, name, source_name, selected):
        bundle = self.root / "bundles" / name
        source_root = self.inputs[source_name]["root"]
        source_manifest = self.manifests[source_name]
        manifest = load_json(bundle / "manifest.json")
        self.manifest_schema.validate(manifest)
        self.check(manifest["page_ids"] == selected, f"{name}: exact selected page IDs")
        self.check([record["id"] for record in manifest["pages"]] == selected,
                   f"{name}: exact page manifest order")
        self.check(manifest["source"]["dataset_id"] == source_manifest["dataset_id"],
                   f"{name}: source dataset identity")
        source_copy = self.reference(bundle, manifest["source"]["manifest"])
        self.check(digest(source_copy) == digest(source_root / "manifest.json"),
                   f"{name}: source manifest copied as original bytes")
        validation = load_json(self.reference(bundle, manifest["source"]["validation"]))
        self.check(validation.get("status") == "pass" and not validation.get("errors"),
                   f"{name}: recorded complete source validation passed")
        checks = validation.get("checks", [])
        names = [check["name"] for check in checks]
        required = {f"{kind}:{record['id']}" for record in source_manifest["pages"]
                    for kind in ("page", "page_files")} | {"exports", "export_inventory"}
        self.check(len(names) == len(set(names)) and required <= set(names)
                   and all(check["status"] == "pass" for check in checks),
                   f"{name}: source validation covers every one of {len(source_manifest['pages'])} pages")
        generator = manifest["generator"]
        self.check(generator["commit"] == self.state["commit"] and generator["dirty"] is False,
                   f"{name}: exporter records the frozen clean commit")
        self.check(load_json(self.reference(bundle, generator["environment"])) == self.projection_environment,
                   f"{name}: exporter records frozen environment and independently hashed projection modules")
        for key, source_relative in (("xsd", "schemas/xml/page-2019-07-15.xsd"),
                                     ("license", "schemas/xml/PAGE-LICENSE"),
                                     ("provenance", "schemas/xml/provenance.json")):
            self.check(digest(self.reference(bundle, manifest["schema"][key])) == digest(ROOT / source_relative),
                       f"{name}: pinned schema {key} copied unchanged")
        source_records = {record["id"]: (index, record)
                          for index, record in enumerate(source_manifest["pages"])}
        summaries = []
        for record in manifest["pages"]:
            page_id = record["id"]
            source_index, source_record = source_records[page_id]
            canonical_path = safe_file(source_root, source_record["path"])
            self.check(record["source_index"] == source_index, f"{name}/{page_id}: source index")
            self.check(digest(canonical_path) == source_record["sha256"],
                       f"{name}/{page_id}: frozen canonical digest")
            page = load_json(canonical_path)
            expected = canonical_observation(page)
            self.check(record["xml"]["path"] == f"{page_id}.xml"
                       and record["canonical"]["path"] == f"provenance/pages/{page_id}.json"
                       and record["report"]["path"] == f"reports/{page_id}.json"
                       and record["image"]["path"] == f"images/{page_id}.png",
                       f"{name}/{page_id}: fixed portable bundle paths")
            copied_canonical = self.reference(bundle, record["canonical"])
            self.check(digest(copied_canonical) == digest(canonical_path),
                       f"{name}/{page_id}: canonical copied as original bytes")
            image = self.reference(bundle, record["image"])
            source_image = safe_file(source_root, page["image"]["path"])
            self.check(digest(image) == digest(source_image) == page["image"]["sha256"],
                       f"{name}/{page_id}: raw source PNG bytes copied unchanged")
            self.check([record["image"][axis] for axis in ("width", "height")]
                       == [page["image"][axis] for axis in ("width", "height")],
                       f"{name}/{page_id}: declared image dimensions")
            xml = self.reference(bundle, record["xml"]).read_bytes()
            actual = read_page(xml)
            self.check(set(actual) == set(expected), f"{name}/{page_id}: complete independent observation")
            for field in expected:
                self.check(actual[field] == expected[field], f"{name}/{page_id}: canonical equality for {field}")
            self.check(safe_file(bundle, actual["image"]["filename"]) == image,
                       f"{name}/{page_id}: relative imageFilename resolves to copied PNG")
            parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
            self.xsd.assertValid(etree.fromstring(xml, parser))
            self.check(True, f"{name}/{page_id}: independent pinned PAGE 2019 XSD passed")
            page_report = load_json(self.reference(bundle, record["report"]))
            self.page_report_schema.validate(page_report)
            mapping = {identifier: identifier[2:] for collection in expected["geometry"].values()
                       for identifier in collection}
            self.check(page_report["page_id"] == page_id
                       and page_report["image_filename"] == expected["image"]["filename"]
                       and page_report["id_mapping"] == mapping,
                       f"{name}/{page_id}: exact canonical ID mapping and declared projection losses")
            summary = {"page_id": page_id, "titles": sum(block["category"] == "titre" for block in page["blocks"]),
                       "lines_with_article": sum(len(region["lines"]) for region in expected["reading"]["text_regions_in_order"]),
                       "words": len(page["words"]), "advert_ranks": expected["reading"]["advert_ranks"],
                       "region_types": {kind: list(expected["region_types"].values()).count(kind)
                                        for kind in sorted(set(expected["region_types"].values()))}}
            if source_name == "legacy":
                self.check(summary["titles"] == 26 and summary["lines_with_article"] == 535
                           and len(summary["advert_ranks"]) == 14,
                           f"{name}/{page_id}: 26 titles, 535 lines with article, 14 exact canonical advert ranks")
            summaries.append(summary)
        artifacts = manifest["artifacts"]
        artifact_paths = [item["path"] for item in artifacts]
        inventory = snapshot(bundle)
        actual_paths = {relative for relative, item in inventory.items() if item["kind"] == "file"}
        self.check(len(artifact_paths) == len(set(artifact_paths))
                   and set(artifact_paths) | {"manifest.json"} == actual_paths
                   and "manifest.json" not in artifact_paths,
                   f"{name}: complete exact artifact file inventory")
        for artifact in artifacts:
            path = self.reference(bundle, artifact)
            self.check(path.stat().st_size == artifact["size_bytes"],
                       f"{name}: declared byte length {artifact['path']}")
        self.report["bundles"][name] = {"path": bundle.relative_to(self.root).as_posix(),
                                       "pages": summaries, "snapshot": inventory}
        return bundle

    def execute(self):
        self.check(len(self.manifests["legacy"]["pages"]) == 100, "Historical source contains exactly 100 pages")
        self.check(LEGACY_PAGE in {page["id"] for page in self.manifests["legacy"]["pages"]},
                   "Historical selection mf_0003 exists")
        layout_ids = [page["id"] for page in self.manifests["layout"]["pages"]]
        self.check(len(layout_ids) == 2 and len(set(layout_ids)) == 2, "Layout source contains exactly two pages")
        (self.root / "bundles").mkdir()
        for name, source_name, selected in (("legacy", "legacy", [LEGACY_PAGE]),
                                             ("layout", "layout", layout_ids),
                                             ("layout-repeat", "layout", layout_ids)):
            arguments = ["export-newseye", "--from", self.inputs[source_name]["root"],
                         "--output", self.root / "bundles" / name]
            if source_name == "legacy":
                arguments += ["--page", LEGACY_PAGE]
            self.run(f"export-{name}", arguments, selected=selected)
            bundle = self.inspect_bundle(name, source_name, selected)
            self.run(f"validate-{name}", ["validate", bundle], selected=selected)
            self.check(snapshot(bundle) == self.report["bundles"][name]["snapshot"],
                       f"{name}: validate is read-only")
        self.check(snapshot(self.root / "bundles/layout") == snapshot(self.root / "bundles/layout-repeat"),
                   "Repeated layout export: entire file/directory inventory and every byte identical")
        source = self.inputs["layout"]["root"]
        unknown = "unknown_page_for_newseye_acceptance"
        self.check(unknown not in layout_ids, "Negative unknown page is absent from the source")
        for name, selection in (("unknown", [unknown]), ("duplicate", [layout_ids[0], layout_ids[0]])):
            destination = self.root / f"must-not-exist-{name}"
            arguments = ["export-newseye", "--from", source, "--output", destination]
            for page_id in selection:
                arguments += ["--page", page_id]
            self.run(f"reject-{name}-page", arguments, failure=True)
            self.check(not destination.exists(), f"{name}: rejection before destination creation")
        nested = source / "__newseye_acceptance_forbidden_output__"
        self.check(not nested.exists(), "Nested negative destination is initially absent")
        self.run("reject-nested-output", ["export-newseye", "--from", source, "--output", nested], failure=True)
        self.check(not nested.exists(), "Nested output refused before any source write")
        existing = self.root / "bundles/layout"
        before = snapshot(existing)
        self.run("reject-existing-output", ["export-newseye", "--from", source, "--output", existing], failure=True)
        self.check(snapshot(existing) == before, "Existing destination preserved in full after refusal")
        self.guard()
        self.report["status"] = "pass"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--layout-source", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        if output.exists() or args.output.is_symlink():
            raise ValueError(f"Destination exists; no overwrite: {output}")
        state = source_state()
        if state["dirty"]:
            raise ValueError("A clean committed source revision is required")
        roots = {"legacy": args.legacy_source.resolve(), "layout": args.layout_source.resolve()}
        for name, root in roots.items():
            if not root.is_dir():
                raise ValueError(f"Missing {name} source directory: {root}")
            if output.is_relative_to(root) or root.is_relative_to(output):
                raise ValueError("Acceptance output and all source lots must be disjoint")
        if roots["legacy"].is_relative_to(roots["layout"]) or roots["layout"].is_relative_to(roots["legacy"]):
            raise ValueError("The two input lots must be disjoint")
        free = shutil.disk_usage(existing_ancestor(output)).free
        if free < MIN_FREE:
            raise ValueError(f"At least {MIN_FREE} free output bytes required; found {free}")
        # Establish the historical anchors before mkdir or any campaign write.
        inputs = {name: {"root": root, "anchor": anchor_source(name, root, state["commit"]),
                         "snapshot": snapshot(root)} for name, root in roots.items()}
        acceptance = Acceptance(output, state, inputs)
    except Exception as exc:
        print(f"Refus avant écriture : {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    output.mkdir(parents=True)
    try:
        acceptance.execute()
    except (Exception, KeyboardInterrupt) as exc:
        acceptance.report["errors"].append(f"{type(exc).__name__}: {exc}")
        # Try to record a source/resource violation even when a command failed first.
        try:
            acceptance.guard()
        except Exception as guard_exc:
            acceptance.report["errors"].append(f"Final guard: {type(guard_exc).__name__}: {guard_exc}")
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    acceptance.report["resources"] = {
        "child_maxrss_raw": usage.ru_maxrss,
        "child_maxrss_unit": "bytes" if sys.platform == "darwin" else "KiB",
        "written_bytes_before_final_report": volume(output), "limit_bytes": MAX_BYTES,
        "minimum_free_bytes": MIN_FREE, "scope": "Between commands; not an atomic subprocess quota",
    }
    report_path = output / "acceptance.json"
    write_json(report_path, acceptance.report)
    final_size, final_free = volume(output), shutil.disk_usage(output).free
    if final_size >= MAX_BYTES or final_free < MIN_FREE:
        acceptance.report["status"] = "fail"
        acceptance.report["errors"].append(f"Final resource guard: {final_size} bytes output, {final_free} bytes free")
        write_json(report_path, acceptance.report)
    print(json.dumps({"status": acceptance.report["status"], "path": str(report_path),
                      "external_reader": "not_evaluated", "model_evaluation": "not_evaluated",
                      "visual_review": "not_run", "errors": acceptance.report["errors"]}, ensure_ascii=False))
    return 0 if acceptance.report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
