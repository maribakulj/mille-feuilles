#!/usr/bin/env python3
"""Small A1 CLI acceptance from four selected canonical pages, with no rendering.

The campaign reaggregates report observations independently; it does not rerun
the measurement engine or validate complete datasets. Source monitoring covers
only the two native manifests and the four selected canonical files. No image,
asset, export or corpus file is read. Preserve all campaign evidence on failure.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

from jsonschema import Draft202012Validator

from mille_feuilles.io import ROOT
from mille_feuilles.validation import validate_page

RESERVE = 500_000_000
MAX_CAMPAIGN = 20_000_000
REFERENCE = "as:XIXe"
ARCHIVES = {
    "legacy": "docs/reports/pilot-manifest.json",
    "layout": "docs/reports/lot4/acceptance/lots/compact-identity-x2/manifest.json",
}
PINNED = {
    "calibrer": ("tools/cadrage/calibrer.py", "8b72e367424b6f8825539c46e349e2d948b942ff5412fd61a884fd4804ef820d"),
    "calibration": ("tools/cadrage/sortie/calibration.json", "6349af2f15c39f0203ffdf873b07d07454a8a3671bab9ee28b5b637ecf731c08"),
}
CHECKS = {"selected_canonicals", "pinned_measurement", "report_schema", "source_stability", "output_hash"}
PHYSICAL = {"page_largeur_cm", "page_hauteur_cm", "colonne_largeur_cm", "gouttiere_mm",
            "interligne_pt_med_page", "ligne_hauteur_mm_med_page"}
PIXELS = {"ligne_hauteur_px_med_page", "interligne_px_med_page"}
COUNT_NAMES = {"blocs_nombre", "blocs_surface", "ordre_transitions"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_bytes(), object_pairs_hook=unique)

    def finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError(f"Nonfinite JSON number in {path}")
        if isinstance(item, (list, dict)):
            for child in item.values() if isinstance(item, dict) else item:
                finite(child)
    finite(value)
    return value


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                               allow_nan=False) + "\n", encoding="utf-8")


def file_record(root, relative):
    path = root / relative
    if (Path(relative).is_absolute() or ".." in Path(relative).parts
            or not path.resolve().is_relative_to(root.resolve()) or path.is_symlink()):
        raise ValueError(f"Unsafe file reference: {relative}")
    return {"path": relative, "sha256": digest(path), "size_bytes": path.stat().st_size}


def environment():
    modules = ("realism.py", "structure_report.py", "validation.py", "io.py")
    schemas = ("manifest.schema.json", "page.schema.json", "structure-report.schema.json")
    return {"python": sys.version,
            "packages": {name: importlib.metadata.version(name)
                         for name in ("Pillow", "numpy", "fonttools", "lxml", "jsonschema", "shapely")},
            "modules": {name: digest(ROOT / "src/mille_feuilles" / name) for name in modules},
            "schemas": {name: digest(ROOT / "schemas" / name) for name in schemas}}


def state():
    return {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
            "environment": environment(), "cli_sha256": digest(ROOT / "src/mille_feuilles/cli.py"),
            "acceptance_script_sha256": digest(Path(__file__).resolve()),
            "references": {key: file_record(ROOT, relative) for key, (relative, _) in PINNED.items()}}


def selected_input(name, root, commit):
    """Open no documentary file except manifest.json and the selected canonicals."""
    archived = subprocess.check_output(["git", "show", f"{commit}:{ARCHIVES[name]}"], cwd=ROOT)
    archive_sha = hashlib.sha256(archived).hexdigest()
    manifest_ref = file_record(root, "manifest.json")
    if manifest_ref["sha256"] != archive_sha or digest(ROOT / ARCHIVES[name]) != archive_sha:
        raise ValueError(f"{name}: source manifest differs from its committed historical archive")
    manifest = load(root / "manifest.json")
    wanted = {"mf_0000", "mf_0003"} if name == "legacy" else {item["id"] for item in manifest["pages"]}
    if len(manifest["pages"]) != (100 if name == "legacy" else 2) or len(wanted) != 2:
        raise ValueError(f"{name}: unexpected historical source or selected page count")
    chosen = [(index, item) for index, item in enumerate(manifest["pages"]) if item["id"] in wanted]
    if len(chosen) != 2 or {item["id"] for _, item in chosen} != wanted:
        raise ValueError(f"{name}: missing or duplicate selected page")
    fingerprints, pages = {"manifest.json": manifest_ref}, []
    for index, record in chosen:
        if record["path"] != f"pages/{record['id']}.json":
            raise ValueError("Unexpected selected canonical path")
        fingerprint = file_record(root, record["path"])
        if fingerprint["sha256"] != record["sha256"]:
            raise ValueError(f"Canonical SHA mismatch: {record['id']}")
        fingerprints[record["path"]] = fingerprint
        page = load(root / record["path"])
        issues = validate_page(page)
        if issues:
            raise ValueError(f"Selected canonical invalid: {record['id']}: {issues[:3]}")
        if page["page_id"] != record["id"]:
            raise ValueError("Canonical identifier mismatch")
        pages.append((index, fingerprint, page))
    return {"root": root, "manifest": manifest, "files": fingerprints, "pages": pages,
            "historical_anchor": {"archive": ARCHIVES[name], "commit": commit, "sha256": archive_sha}}


def distribution(values):
    """Independent transcription of the pinned q definition, not an engine call."""
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        return {"n": 0}
    if count == 1:
        return {"n": 1, "p50": round(ordered[0], 4)}
    quantiles = statistics.quantiles(ordered, n=20, method="inclusive")
    result = {"n": count, "moy": round(statistics.fmean(ordered), 4),
              "min": round(ordered[0], 4), "max": round(ordered[-1], 4)}
    result.update({f"p{percent}": round(quantiles[percent // 5 - 1], 4)
                   for percent in (10, 25, 50, 75, 90)})
    return result


def reaggregate(rows):
    """Pool raw observations and sum raw counts before any rounding or division."""
    values, counts = defaultdict(list), defaultdict(lambda: defaultdict(float))
    for row in rows:
        for name, items in row["values"].items():
            values[name].extend(items)
        for name, categories in row["counts"].items():
            bucket = counts[name]
            for category, number in categories.items():
                bucket[category] += number
    if set(values) & set(counts):
        raise ValueError("A metric cannot be both a distribution and counts")
    result = {name: distribution(items) for name, items in values.items()}
    for name, categories in counts.items():
        total = sum(categories.values()) or 1
        result[name] = {category: {"valeur": round(number, 4), "part": round(number / total, 4)}
                        for category, number in categories.items()}
    return result


def page_metadata(index, canonical, page):
    params = page["provenance"]["parameters"]
    layout = params.get("layout")
    return {"id": page["page_id"], "source_index": index, "canonical": canonical,
            "schema_version": page["schema_version"], "profile": page["profile"],
            "width": page["image"]["width"], "height": page["image"]["height"],
            "declared_dpi": page["image"]["dpi"], "columns_declared": params.get("columns"),
            "layout_columns_declared": None if layout is None else {
                zone["id"]: len(zone["columns"]) for zone in layout["zones"]},
            "oversampling": params.get("oversampling"), "angle_degrees": params.get("angle_degrees"),
            "partition": params.get("partition"),
            "template_article_ids": page["provenance"].get("extensions", {}).get("mf:template_article_ids")}


class Acceptance:
    def __init__(self, output, frozen, inputs):
        self.root, self.frozen, self.inputs = output, frozen, inputs
        self.schema = Draft202012Validator(load(ROOT / "schemas/structure-report.schema.json"))
        self.calibration = load(ROOT / PINNED["calibration"][0])
        self.report = {"format": "mille-feuilles-structure-acceptance", "version": "1", "status": "fail",
                       "started_at_utc": datetime.now(timezone.utc).isoformat(), "source": frozen,
                       "inputs": {name: {"path": str(item["root"]), "files_monitored": item["files"],
                                          "historical_anchor": item["historical_anchor"]}
                                  for name, item in inputs.items()},
                       "checks": [], "commands": [], "reports": {}, "errors": [],
                       "scope": {"source_monitoring": "native manifests and four selected canonicals only",
                                 "aggregate_check": "independent reconstruction from per_page, not a second measurement engine",
                                 "dataset_validation": "not_performed", "pixels": "not_read_or_compared",
                                 "corpus_access": "not_performed", "realism_verdict": "not_evaluated"},
                       "limits": {"campaign_bytes": MAX_CAMPAIGN, "reserve_bytes": RESERVE,
                                  "scope": "checks between commands and after final report, not an atomic quota"}}

    def check(self, condition, message):
        if not condition:
            raise ValueError(message)
        self.report["checks"].append(message)

    def guard(self):
        self.check(state() == self.frozen, "Clean commit, code, schema, reference and environment unchanged")
        for name, item in self.inputs.items():
            self.check(all(file_record(item["root"], relative) == record
                           for relative, record in item["files"].items()),
                       f"{name}: monitored manifest and two canonicals unchanged")
        size = sum(path.stat().st_size for path in self.root.rglob("*") if path.is_file())
        self.check(size < MAX_CAMPAIGN and shutil.disk_usage(self.root).free >= RESERVE,
                   f"Campaign resource guard: {size} bytes, reserve at least {RESERVE}")

    def run(self, name, source, destination, selection, *, failure=False):
        self.guard()
        argv = [sys.executable, "-m", "mille_feuilles.cli", "report-structure", "--from", str(source),
                "--output", str(destination), "--reference", REFERENCE, *selection]
        out, err = self.root / f"logs/{name}.json", self.root / f"logs/{name}.stderr.log"
        entry = {"name": name, "argv": argv, "cwd": str(ROOT),
                 "stdout": out.relative_to(self.root).as_posix(), "stderr": err.relative_to(self.root).as_posix()}
        self.report["commands"].append(entry)
        print(f"Acceptation structure A1 : {name}", file=sys.stderr, flush=True)
        started = time.perf_counter()
        with out.open("xb") as stdout, err.open("xb") as stderr:
            completed = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
        entry.update(exit_code=completed.returncode, elapsed_seconds=time.perf_counter() - started)
        self.guard()
        self.check(completed.returncode == (2 if failure else 0), f"{name}: expected exit code")
        if failure:
            self.check(out.stat().st_size == 0 and not destination.exists(),
                       f"{name}: refusal without success JSON or destination")
            return None
        result = load(out)
        checks = result.get("checks", [])
        names = [item["name"] for item in checks]
        self.check(result.get("status") == "pass" and result.get("errors") == []
                   and len(names) == len(set(names)) and set(names) == CHECKS
                   and all(item["status"] == "pass" for item in checks), f"{name}: named CLI checks passed")
        return result

    def inspect_variant(self, label, variant, pages, without_template, reference):
        excluded = [page["page_id"] for page in pages if without_template and
                    "mf:template_article_ids" not in page["provenance"].get("extensions", {})]
        by_id = {page["page_id"]: page for page in pages}
        measured = [page["page_id"] for page in pages if page["page_id"] not in excluded]
        self.check([row["page_id"] for row in variant["per_page"]] == measured
                   and [row["page_id"] for row in variant["excluded"]] == excluded,
                   f"{label}: exact measured/excluded partition in source order")
        self.check(variant["role"] == ("sensitivity" if without_template else "primary")
                   and variant["cohort_status"] == ("ND" if excluded else "complete"),
                   f"{label}: cohort status and role match canonical template identification")
        for row in variant["per_page"]:
            page = by_id[row["page_id"]]
            removed = page["provenance"]["extensions"]["mf:template_article_ids"] if without_template else []
            blocks = [block["id"] for block in page["blocks"] if block["article_id"] in removed]
            has_autre = any(block["category"] == "autre" and block["id"] not in blocks for block in page["blocks"])
            self.check(row["removed_article_ids"] == removed and row["removed_block_ids"] == blocks
                       and row["has_autre"] == has_autre, f"{label}/{row['page_id']}: exact canonical template removal")
        stats = reaggregate(variant["per_page"])
        self.check(stats == variant["partial_stats" if excluded else "stats"],
                   f"{label}: all aggregates independently reconstructed from raw per_page observations")
        if excluded:
            self.check(variant["stats"] is None and variant["comparison"] is None,
                       f"{label}: whole incomplete cohort ND, no partial-cohort comparison")
            return
        comparison = variant["comparison"]
        self.check(set(stats) | set(reference) <= set(comparison),
                   f"{label}: comparison covers every observed and archived metric")
        for name, entry in comparison.items():
            self.check(entry["mf"] == stats.get(name) and entry["real"] == reference.get(name),
                       f"{label}/{name}: comparison uses exact reconstructed and archived statistics")
            if entry["status"] in {"ND", "NC"}:
                self.check(not entry["comparison_allowed"], f"{label}/{name}: ND/NC not compared")
            if entry["comparison_allowed"] and entry["kind"] == "distribution":
                value, real = entry["mf"]["p50"], entry["real"]
                position = "< p10" if value < real["p10"] else "> p90" if value > real["p90"] else "p10–p90"
                self.check(entry["position"] == position, f"{label}/{name}: descriptive position, inclusive endpoints")
            if name in COUNT_NAMES:
                self.check(entry["kind"] == "counts", f"{label}/{name}: category counts keep their own representation")
        self.check(all(comparison[name]["definition_status"] == "ND"
                       and comparison[name]["status"] == "ND" and comparison[name]["mf"] is None
                       and not comparison[name]["comparison_allowed"] for name in PHYSICAL),
                   f"{label}: physical measurements unavailable, declared DPI not used")
        self.check(all(comparison[name]["definition_status"] == "A"
                       and not comparison[name]["comparison_allowed"] for name in PIXELS),
                   f"{label}: pixel measures reported without comparison across resolutions")

    def inspect(self, name, source_name, mode, receipt):
        directory = self.root / "reports" / name
        self.check({path.name for path in directory.iterdir()} == {"report.json", "report.sha256"},
                   f"{name}: exactly two report files")
        report_path = directory / "report.json"
        report_sha = digest(report_path)
        self.check((directory / "report.sha256").read_bytes() == f"{report_sha}  report.json\n".encode("ascii")
                   and receipt["report_sha256"] == report_sha and Path(receipt["report_path"]) == report_path,
                   f"{name}: detached digest and CLI receipt match actual bytes")
        report = load(report_path)
        self.schema.validate(report)
        self.check(report["generator"] == {key: self.frozen[key] for key in ("commit", "dirty", "environment")},
                   f"{name}: exact frozen code/schema/package environment")
        source = self.inputs[source_name]
        manifest = source["manifest"]
        expected_source = {key: manifest[key] for key in ("dataset_id", "schema_version", "profile")}
        expected_source.update(manifest=source["files"]["manifest.json"], total_pages=len(manifest["pages"]))
        self.check(report["inputs"] == {"source": expected_source, **self.frozen["references"]},
                   f"{name}: exact selected source and pinned-reference provenance")
        metadata = [page_metadata(*item) for item in source["pages"]]
        ids = [item["id"] for item in metadata]
        self.check(report["selection"] == {"mode": mode, "page_ids": ids, "pages": metadata}
                   and receipt["selected_page_ids"] == ids,
                   f"{name}: exact selection, source_index and native declared metadata")
        archived_pages = [page for page in self.calibration["pages"]
                          if page["source"] == "as" and page["epoch"] == "XIXe"]
        columns = defaultdict(Counter)
        for page in archived_pages:
            columns[page["split"]][str(page["colonnes"])] += 1
        ref = report["reference"]
        self.check(ref["cohort"] == REFERENCE and ref["calibration_sha256"] == PINNED["calibration"][1]
                   and ref["stats"] == self.calibration["stats"][REFERENCE]
                   and ref["pages"] == len(archived_pages) == 65
                   and ref["pages_by_split"] == dict(Counter(page["split"] for page in archived_pages))
                   and ref["columns_by_split"] == {split: dict(items) for split, items in columns.items()},
                   f"{name}: archived AS XIXe statistics and 65-page train/dev cohort unchanged")
        pages = [item[2] for item in source["pages"]]
        for variant_name, variant in report["variants"].items():
            self.inspect_variant(f"{name}/{variant_name}", variant, pages,
                                 variant_name == "sans_gabarit", ref["stats"])
        self.report["reports"][name] = {"path": report_path.relative_to(self.root).as_posix(),
                                       "sha256": report_sha, "selected_page_ids": ids,
                                       "cohorts": {key: value["cohort_status"] for key, value in report["variants"].items()}}

    def execute(self):
        (self.root / "logs").mkdir()
        (self.root / "reports").mkdir()
        for name, source_name, selection, mode in (
            ("layout", "layout", ["--all-pages"], "all"),
            ("legacy", "legacy", ["--page", "mf_0003", "--page", "mf_0000"], "explicit"),
            ("layout-repeat", "layout", ["--all-pages"], "all"),
        ):
            receipt = self.run(name, self.inputs[source_name]["root"], self.root / "reports" / name, selection)
            self.inspect(name, source_name, mode, receipt)
        for filename in ("report.json", "report.sha256"):
            self.check((self.root / "reports/layout" / filename).read_bytes()
                       == (self.root / "reports/layout-repeat" / filename).read_bytes(),
                       f"Repeated compact report: {filename} byte-identical")
        source = self.inputs["layout"]["root"]
        first_id = self.inputs["layout"]["pages"][0][2]["page_id"]
        unknown = "unknown_page_for_structure_acceptance"
        self.check(unknown not in {item["id"] for item in self.inputs["layout"]["manifest"]["pages"]},
                   "Unknown-page negative identifier is absent")
        for name, selection in (("unknown", ["--page", unknown]),
                                ("duplicate", ["--page", first_id, "--page", first_id]),
                                ("no-selection", [])):
            self.run(f"reject-{name}", source, self.root / f"must-not-exist-{name}", selection, failure=True)
        nested = source / "__structure_acceptance_forbidden_output__"
        self.check(not nested.exists(), "Nested negative destination initially absent")
        self.run("reject-nested", source, nested, ["--all-pages"], failure=True)
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
            raise ValueError("Acceptance destination must be new")
        ancestor = output.parent
        while not ancestor.exists():
            ancestor = ancestor.parent
        if shutil.disk_usage(ancestor).free < RESERVE:
            raise ValueError(f"At least {RESERVE} bytes free required; no campaign destination created")
        frozen = state()
        if frozen["dirty"]:
            raise ValueError("A clean committed source revision is required")
        for key, (_, expected_sha) in PINNED.items():
            if frozen["references"][key]["sha256"] != expected_sha:
                raise ValueError(f"Pinned {key} differs")
        roots = {"legacy": args.legacy_source.resolve(), "layout": args.layout_source.resolve()}
        for root in roots.values():
            if output.is_relative_to(root) or root.is_relative_to(output):
                raise ValueError("Acceptance output and source lots must be disjoint")
        inputs = {name: selected_input(name, root, frozen["commit"]) for name, root in roots.items()}
        acceptance = Acceptance(output, frozen, inputs)
        if state() != frozen or any(
            file_record(item["root"], relative) != record
            for item in inputs.values() for relative, record in item["files"].items()
        ):
            raise ValueError("Selected inputs, code or reference changed during preflight")
        if shutil.disk_usage(ancestor).free < RESERVE:
            raise ValueError("Required reserve no longer available before mkdir")
    except Exception as exc:
        print(f"Refus avant écriture : {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    output.mkdir(parents=True)
    try:
        acceptance.execute()
    except (Exception, KeyboardInterrupt) as exc:
        acceptance.report["errors"].append(f"{type(exc).__name__}: {exc}")
        try:
            acceptance.guard()
        except Exception as guard_exc:
            acceptance.report["errors"].append(f"Final guard: {type(guard_exc).__name__}: {guard_exc}")
    destination = output / "acceptance.json"
    write(destination, acceptance.report)
    size = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    if size >= MAX_CAMPAIGN or shutil.disk_usage(output).free < RESERVE:
        acceptance.report["status"] = "fail"
        acceptance.report["errors"].append("Final campaign size or reserve guard failed")
        write(destination, acceptance.report)
    print(json.dumps({"status": acceptance.report["status"], "path": str(destination),
                      "realism_verdict": "not_evaluated", "errors": acceptance.report["errors"]}, ensure_ascii=False))
    return 0 if acceptance.report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
