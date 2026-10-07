#!/usr/bin/env python3
"""Accept measured CLI generation after committing and freezing the source.

  .venv/bin/python tools/accept_measured.py --output runs/accept-measured

The output must not exist. Preflight requires clean Git and at least 800 MB
free before mkdir. Six one-page lots are generated: both measured presets at
800x1100 with oversampling 1/2, then both at 2680x3698 with oversampling 2.
The compact controlled x2 lot is replayed with jobs=2 from its own assets and
reproduced sequentially: eight rendered pages in total. Only bundled original
demonstration assets are used. All outputs survive a failure; nothing is removed.

Command timings include generation, exports and validation. RUSAGE_CHILDREN
ru_maxrss is recorded as a cumulative high-water mark, NEVER a difference or a
per-command peak (macOS: bytes; Linux: KiB). The 150 MB footprint limit is checked
before/after each command and at completion. Stopping occurs between commands:
a running subprocess can exceed it; this is not an atomic disk quota. A technical
pass leaves visual review explicitly NOT RUN; inspect
the listed page images and severity sheets separately. No historical calibration
or OCR gain is asserted. Exit codes: 0 technical pass, 1 failure, 2 preflight refusal.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit

from PIL import Image

from mille_feuilles.catalog import load_catalog
from mille_feuilles.degrade import check_profile, load_profile, profile_sha256
from mille_feuilles.pipeline import environment
from mille_feuilles.render import PROFILE_MEASURED
from mille_feuilles.validation import load_json, safe_path


REPO = Path(__file__).resolve().parents[1]
MIN_FREE = 800_000_000
MAX_BYTES = 150_000_000
SEED = 20261009
PRESETS = ("identity", "controlled-v1")
LABELS = ("readable", "uncertain", "illegible")
BUILTIN_TEXTS = {"text_demo_fr", "text_titres_fr", "text_annonces_fr"}


def ensure(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def write_json(path, value):
    write_new(path, encoded(value))


def snapshot(root):
    return {p.relative_to(root).as_posix(): digest(p)
            for p in sorted(root.rglob("*")) if p.is_file()}


def code_snapshot():
    return {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                          text=True).strip(),
        "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"],
                                              cwd=REPO, text=True).strip()),
        "script_sha256": digest(Path(__file__)),
        "reproduce_script_sha256": digest(REPO / "tools/reproduce_pilot.py"),
        "python": sys.version, "executable": sys.executable,
    }


def original_input_paths():
    """Name only catalogued builtin assets/evidence and the two preset files."""
    catalog = load_catalog(REPO)
    texts = [item for item in catalog["assets"] if item["kind"] == "text"]
    ensure({item["id"] for item in texts} == BUILTIN_TEXTS,
           "Acceptance requires exactly the three bundled original text assets")
    ensure(all(item["metadata"].get("historical_corpus") is False and
               item["metadata"].get("content_type") == "original_synthetic_demonstration"
               for item in texts), "A source text is not labelled original demonstration")
    paths = {"assets/catalog.json", *(f"profiles/{name}.json" for name in PRESETS)}
    for item in catalog["assets"]:
        paths.add(item["path"])
        paths.update(record["path"] for record in item["metadata"].get("evidence_files", []))
        if not urlsplit(item["rights"]["evidence_uri"]).scheme:
            paths.add(item["rights"]["evidence_uri"])
    return sorted(paths)


def input_snapshot(paths):
    return {relative: digest(safe_path(REPO, relative)) for relative in paths}


def child_usage():
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    unit = "bytes" if sys.platform == "darwin" else "KiB" if sys.platform.startswith("linux") else None
    ensure(unit is not None, "ru_maxrss units are only defined here for macOS and Linux")
    return {
        "ru_maxrss_raw": usage.ru_maxrss, "ru_maxrss_unit": unit,
        "ru_maxrss_bytes": int(usage.ru_maxrss * (1024 if unit == "KiB" else 1)),
        "user_cpu_seconds": usage.ru_utime, "system_cpu_seconds": usage.ru_stime,
        "scope": "RUSAGE_CHILDREN cumulative maximum; not a delta or per-command peak",
    }


def composition(page):
    value = {key: deepcopy(page[key]) for key in (
        "articles", "blocks", "lines", "words", "reading_order"
    )}
    for item in value["lines"] + value["words"]:
        item.pop("legibility")
    value["text_spans"] = page["provenance"]["text_spans"]
    return value


class Acceptance:
    def __init__(self, root, code, frozen_environment, inputs):
        self.root, self.code = root, code
        self.frozen_environment, self.inputs = frozen_environment, inputs
        self.report = {
            "format": "mille-feuilles-measured-acceptance", "version": "1", "status": "fail",
            "seed": SEED, "commands": [], "checks": [], "errors": [], "lots": {}, "pairs": [],
            "volume_checks": [],
            "volume_limit_note": "Checked between commands and at completion; no atomic subprocess quota",
            "scope": "Technical acceptance using bundled original demonstration assets only",
            "visual_review": {"status": "not_run", "targets": [],
                              "note": "Required separately; no image was visually accepted by this script"},
            "legibility_note": "Heuristic observations only; no required random label frequency or OCR claim",
            "resource_note": "Command time includes exports/validation; child ru_maxrss is cumulative, not per-command",
            "planned_counts": {"base_pages": 6, "replay_pages": 1, "reproduced_pages": 1},
        }

    def check(self, condition, label):
        ensure(condition, label)
        self.report["checks"].append(label)

    def frozen(self, label):
        self.check(code_snapshot() == self.code and not self.code["dirty"],
                   f"{label}: commit, clean Git and script hashes unchanged")
        self.check(environment() == self.frozen_environment, f"{label}: environment unchanged")
        self.check(input_snapshot(self.inputs) == self.inputs, f"{label}: original assets/profiles unchanged")

    def check_volume(self, label):
        total = sum(path.stat().st_size for path in self.root.rglob("*") if path.is_file())
        self.report["volume_checks"].append({
            "stage": label, "written_bytes": total, "limit_bytes": MAX_BYTES,
            "status": "pass" if total < MAX_BYTES else "fail",
        })
        self.check(total < MAX_BYTES,
                   f"{label}: written volume {total} bytes is below {MAX_BYTES} bytes")

    def run(self, name, arguments, script=None):
        self.check_volume(f"before {name}")
        self.frozen(f"before {name}")
        command = [sys.executable]
        command += [str(script)] if script else ["-m", "mille_feuilles.cli"]
        command += [str(arg) for arg in arguments]
        stdout, stderr = f"logs/{name}.stdout.log", f"logs/{name}.stderr.log"
        (self.root / "logs").mkdir(exist_ok=True)
        record = {"name": name, "argv": command, "cwd": str(REPO), "stdout": stdout,
                  "stderr": stderr, "started_at_utc": datetime.now(timezone.utc).isoformat(),
                  "child_usage_before": child_usage()}
        self.report["commands"].append(record)
        print(f"Acceptation mesurée : {name}", file=sys.stderr, flush=True)
        started = time.perf_counter()
        try:
            with (self.root / stdout).open("xb") as out, (self.root / stderr).open("xb") as err:
                result = subprocess.run(command, cwd=REPO, stdout=out, stderr=err, check=False)
            record["exit_code"] = result.returncode
        finally:
            record["elapsed_seconds"] = time.perf_counter() - started
            record["child_usage_after"] = child_usage()
        self.check_volume(f"after {name}")
        self.check(record["exit_code"] == 0, f"{name}: command exited successfully")
        value = load_json(self.root / stdout)
        record["report"] = f"reports/{name}.json"
        write_json(self.root / record["report"], value)
        self.check(isinstance(value, dict) and value.get("status") == "pass",
                   f"{name}: JSON report passed")
        self.frozen(f"after {name}")
        return value

    def generate(self, name, profile, width, height, columns, source=REPO, jobs=1):
        target = self.root / "lots" / name
        result = self.run(f"generate-{name}", [
            "generate", "--output", target, "--assets-root", source, "--pages", 1,
            "--width", width, "--height", height, "--columns", columns, "--dpi", 150,
            "--seed", SEED, "--jobs", jobs, "--degradation-profile", profile,
        ])
        self.check(bool(result.get("checks")) and
                   all(item["status"] == "pass" for item in result["checks"]),
                   f"{name}: every generation validation check passed")
        return target

    def inspect_lot(self, name, root, profile, width, height, columns):
        manifest = load_json(root / "manifest.json")
        inventory = {item["path"]: item["sha256"] for item in manifest["artifacts"]}
        self.check(len(inventory) == len(manifest["artifacts"]), f"{name}: unique artifact inventory")
        actual = snapshot(root)
        self.check(set(actual) - set(inventory) == {"manifest.json", "qa/report.json"}
                   and set(inventory) <= set(actual), f"{name}: inventory covers every generated artifact")
        self.check(all(actual[relative] == sha for relative, sha in inventory.items()),
                   f"{name}: every artifact SHA-256 matches its bytes")

        def reference(item):
            path = safe_path(root, item["path"])
            ensure(digest(path) == item["sha256"] == inventory.get(item["path"]),
                   f"{name}: inconsistent reference {item['path']}")
            return path

        self.check(load_json(root / "environment.json") == self.frozen_environment,
                   f"{name}: recorded environment equals preflight")
        generator = manifest["generator"]
        self.check(generator["commit"] == self.code["commit"] and generator["dirty"] is False,
                   f"{name}: recorded committed clean source")
        reference({"path": generator["environment_path"], "sha256": generator["environment_sha256"]})
        config = load_json(reference(manifest["config"]))
        registry = load_json(reference(manifest["assets"]))
        self.check({item["id"] for item in registry["assets"] if item["kind"] == "text"} == BUILTIN_TEXTS,
                   f"{name}: original builtin text assets only")
        embedded = load_json(reference(manifest["extensions"]["mf:degradation_profile"]))
        self.check(embedded == profile == config["render"]["degradation_profile"],
                   f"{name}: embedded/config/input profile identical")
        self.check(manifest["profile"] == PROFILE_MEASURED and config["pages"] == 1 and
                   all(config["render"][key] == value for key, value in
                       {"width": width, "height": height, "columns": columns, "seed": SEED}.items()),
                   f"{name}: measured one-page configuration matches requested dimensions")
        self.check(len(manifest["pages"]) == 1, f"{name}: exactly one canonical page")
        page = load_json(reference(manifest["pages"][0]))
        reference(page["image"])
        sidecar = page["extensions"]["mf:diagnostics"]
        diagnostic = load_json(reference(sidecar))
        mask = reference({"path": sidecar["mask_path"], "sha256": sidecar["mask_sha256"]})
        for item in diagnostic["inputs"].values():
            reference(item)
        with Image.open(root / page["image"]["path"]) as image:
            self.check(image.mode == "L" and image.size == (width, height), f"{name}: final grayscale dimensions")
        with Image.open(mask) as image:
            self.check(image.mode == "1" and image.size == (width, height), f"{name}: final ideal-mask dimensions")
        labels = {word["id"]: word["legibility"] for word in page["words"]}
        counts = Counter(labels.values())
        counts = {label: counts[label] for label in LABELS}
        self.check(labels == {identity: word["legibility"] for identity, word in diagnostic["words"].items()}
                   and sum(counts.values()) == len(page["words"]) > 0,
                   f"{name}: observed word labels match measured diagnostics")
        self.check(diagnostic["page"]["legibility"] == counts, f"{name}: diagnostic counts agree")
        statistics = load_json(root / "qa/statistics.json")
        measured = statistics["measured_degradations"]
        self.check(measured == {
            "profile": profile["name"], "calibrated": False, "legibility_method": "heuristic-v1",
            "legibility": counts, "pages": [{"page_id": page["page_id"], **diagnostic["page"]}],
        } and statistics["words"] == len(page["words"]), f"{name}: aggregate statistics equal page observations")
        severity = "qa/severity_00.jpg"
        self.check(severity in inventory, f"{name}: severity contact sheet inventoried")
        with Image.open(root / severity) as image:
            self.check(image.format == "JPEG" and image.size == (400, 580), f"{name}: severity sheet decodes")
        self.report["lots"][name] = {
            "path": root.relative_to(self.root).as_posix(), "manifest_sha256": digest(root / "manifest.json"),
            "dataset_id": manifest["dataset_id"], "profile": profile["name"],
            "profile_canonical_sha256": profile_sha256(profile), "oversampling": profile["oversampling"],
            "dimensions": [width, height], "columns": columns, "words": len(page["words"]),
            "legibility": counts, "measurements": diagnostic["page"],
            "bytes": sum(path.stat().st_size for path in root.rglob("*") if path.is_file()),
        }
        self.report["visual_review"]["targets"].extend([
            {"path": (root / relative).relative_to(self.root).as_posix(), "sha256": actual[relative]}
            for relative in (page["image"]["path"], severity)
        ])
        return page

    def pair(self, label, first_root, first, second_root, second):
        ensure(composition(first) == composition(second), f"{label}: composition or source spans changed")
        one = first_root / first["extensions"]["mf:diagnostics"]["mask_path"]
        two = second_root / second["extensions"]["mf:diagnostics"]["mask_path"]
        ensure(one.read_bytes() == two.read_bytes(), f"{label}: ideal mask bytes changed")
        ensure(first["image"]["sha256"] != second["image"]["sha256"], f"{label}: images did not change")
        with Image.open(first_root / first["image"]["path"]) as identity, Image.open(
            second_root / second["image"]["path"]
        ) as controlled:
            ensure(identity.mode == controlled.mode == "L" and identity.size == controlled.size,
                   f"{label}: decoded grayscale image shapes differ")
            shape = list(identity.size)
            identity_pixels, controlled_pixels = identity.tobytes(), controlled.tobytes()
        ensure(identity_pixels != controlled_pixels, f"{label}: decoded pixels did not change")
        self.check(True, f"{label}: identical text/spans/geometry/order/mask, different final images")
        self.report["pairs"].append({
            "name": label, "composition_sha256": hashlib.sha256(encoded(composition(first))).hexdigest(),
            "mask_sha256": digest(one), "identity_image_sha256": first["image"]["sha256"],
            "controlled_image_sha256": second["image"]["sha256"], "status": "pass",
            "decoded_mode": "L", "decoded_size": shape, "decoded_pixels_differ": True,
            "identity_pixels_sha256": hashlib.sha256(identity_pixels).hexdigest(),
            "controlled_pixels_sha256": hashlib.sha256(controlled_pixels).hexdigest(),
        })

    def execute(self):
        write_json(self.root / "reports/code.json", self.code)
        write_json(self.root / "reports/preflight-environment.json", self.frozen_environment)
        write_json(self.root / "sources/original-input-sha256.json", self.inputs)
        write_new(self.root / "sources/builtin-catalog.json", (REPO / "assets/catalog.json").read_bytes())
        profiles = {}
        for preset in PRESETS:
            write_new(self.root / f"sources/profiles/original-{preset}.json",
                      (REPO / f"profiles/{preset}.json").read_bytes())
            original = load_profile(preset)
            for factor in (1, 2):
                profile = deepcopy(original)
                profile["oversampling"] = factor
                check_profile(profile)
                path = self.root / f"sources/profiles/{preset}-x{factor}.json"
                write_json(path, profile)
                profiles[preset, factor] = (path, profile)
        archived_sources = snapshot(self.root / "sources")
        lots, pages = {}, {}
        for size, width, height, columns, factors in (
            ("compact", 800, 1100, 4, (1, 2)), ("pilot-size", 2680, 3698, 6, (2,)),
        ):
            for factor in factors:
                for preset in PRESETS:
                    name = f"{size}-{preset}-x{factor}"
                    path, profile = profiles[preset, factor]
                    lots[name] = self.generate(name, path, width, height, columns)
                    pages[name] = self.inspect_lot(name, lots[name], profile, width, height, columns)
                identity, controlled = (f"{size}-{preset}-x{factor}" for preset in PRESETS)
                self.pair(f"{size}-x{factor}", lots[identity], pages[identity], lots[controlled], pages[controlled])
        source_name = "compact-controlled-v1-x2"
        source, profile = lots[source_name], profiles["controlled-v1", 2][1]
        before = snapshot(source)
        replay = self.generate("compact-controlled-v1-x2-replay", source / "provenance/degradation-profile.json",
                               800, 1100, 4, source=source, jobs=2)
        self.inspect_lot("compact-controlled-v1-x2-replay", replay, profile, 800, 1100, 4)
        comparison = self.run("compare-controlled-replay", ["compare", source, replay])
        self.check(comparison["files_compared"] > 15 and not comparison["mismatches"]
                   and snapshot(replay) == before, "Complete controlled replay is byte-identical, including QA")
        reproduced_root = self.root / "reproduced-controlled-x2"
        reproduced = self.run("reproduce-controlled", [
            source, "--output", reproduced_root, "--report", self.root / "reports/reproduction-proof.json",
        ], script=REPO / "tools/reproduce_pilot.py")
        self.check(reproduced["pages_expected"] == reproduced["pages_reproduced"] == 1 and
                   reproduced["files_compared"] == 2 and not reproduced["mismatches"] and
                   reproduced["environment"]["match"], "Sequential reproduction matches measured PNG/page JSON")
        page = pages[source_name]
        sidecar = page["extensions"]["mf:diagnostics"]
        for relative in (page["image"]["path"], "pages/mf_0000.json", sidecar["path"], sidecar["mask_path"]):
            self.check((source / relative).read_bytes() == (reproduced_root / relative).read_bytes(),
                       f"Reproduced bytes identical: {relative}")
        self.check(snapshot(source) == before, "Replay source lot remained immutable")
        self.check(snapshot(self.root / "sources") == archived_sources, "Archived source profiles remained immutable")
        self.frozen("final")
        final_code, final_environment = code_snapshot(), environment()
        write_json(self.root / "reports/final-code.json", final_code)
        write_json(self.root / "reports/final-environment.json", final_environment)
        self.check(final_code == self.code and final_environment == self.frozen_environment,
                   "Archived final code/environment observations equal preflight")
        self.report["counts"] = {"base_pages": 6, "replay_pages": 1, "reproduced_pages": 1,
                                 "rendered_pages_total": 8, "compared_pairs": 3}
        self.report["child_usage_final"] = child_usage()
        self.report["status"] = "pass"

    def finish(self):
        """Index compact evidence and account for all bytes, including this summary."""
        evidence = [
            {"path": p.relative_to(self.root).as_posix(), "sha256": digest(p), "bytes": p.stat().st_size}
            for p in sorted(self.root.rglob("*")) if p.is_file() and (
                p.suffix == ".json" or p.relative_to(self.root).parts[0] in {"sources", "logs", "reports"}
            )
        ]
        write_json(self.root / "reports/archive-index.json", {
            "format": "mille-feuilles-measured-evidence", "version": "1", "files": evidence,
            "include_also": ["acceptance.json", "reports/archive-index.json"],
            "raster_review_targets": self.report["visual_review"]["targets"],
            "note": "Index only; full generated PNG, masks, XML and fonts remain in this run",
        })
        by_directory = Counter()
        for path in self.root.rglob("*"):
            if path.is_file():
                by_directory[path.relative_to(self.root).parts[0]] += path.stat().st_size
        before = sum(by_directory.values())
        footprint = {"before_summary_bytes": before, "by_top_directory_before_summary": dict(by_directory),
                     "limit_bytes": MAX_BYTES, "total_bytes_including_summary": 0,
                     "measurement": "Sum of regular-file st_size; logical bytes, not allocated disk blocks"}
        self.report["footprint"] = footprint
        for _ in range(10):
            total = before + len(encoded(self.report))
            if total == footprint["total_bytes_including_summary"]:
                break
            footprint["total_bytes_including_summary"] = total
        if total >= MAX_BYTES:
            self.report["status"] = "fail"
            self.report["errors"].append(f"Acceptance footprint exceeds {MAX_BYTES} bytes")
            for _ in range(10):
                total = before + len(encoded(self.report))
                if total == footprint["total_bytes_including_summary"]:
                    break
                footprint["total_bytes_including_summary"] = total
        write_json(self.root / "acceptance.json", self.report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True, help="New, nonexistent acceptance directory")
    args = parser.parse_args(argv)
    root = args.output.absolute()
    try:
        ensure(not root.exists() and not root.is_symlink(), "Output must not exist; no overwrite is allowed")
        parent = root.parent
        while not parent.exists():
            parent = parent.parent
        available = shutil.disk_usage(parent).free
        ensure(available >= MIN_FREE, f"At least {MIN_FREE} free bytes required; found {available}")
        code = code_snapshot()
        ensure(not code["dirty"], "Commit all source changes before acceptance; Git must be clean")
        frozen_environment = environment()
        inputs = input_snapshot(original_input_paths())
        child_usage()  # Refuse an unknown resource-unit convention before any write.
        root.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Refus : {exc}", file=sys.stderr)
        return 2
    acceptance = Acceptance(root, code, frozen_environment, inputs)
    acceptance.report["initial_free_bytes"] = available
    try:
        acceptance.execute()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        acceptance.report["status"] = "fail"
        acceptance.report["errors"].append(f"{type(exc).__name__}: {exc}")
    try:
        acceptance.finish()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Rapport final non écrit : {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": acceptance.report["status"], "report": str(root / "acceptance.json"),
                      "visual_review": "not_run", "errors": acceptance.report["errors"]}, ensure_ascii=False))
    return 0 if acceptance.report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
