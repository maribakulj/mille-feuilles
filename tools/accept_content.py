#!/usr/bin/env python3
"""Compact CLI acceptance of consecutive-v1 on frozen, clean project sources.

Uses only bundled original demonstration texts. Eight pages are rendered in
total, counting replay and reproduction. No output is deleted on failure.
The byte budget is checked between commands, not an atomic subprocess quota.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

from PIL import Image

from mille_feuilles.catalog import text_units
from mille_feuilles.degrade import load_profile
from mille_feuilles.io import ROOT, sha256, write_json
from mille_feuilles.pipeline import environment, git_state
from mille_feuilles.render import PROFILE_LAYOUT
from mille_feuilles.validation import load_json, safe_path

PROFILE = "consecutive-v1"
SEED = 20261007
MAX_BYTES = 200_000_000
RESERVE_BYTES = 500_000_000
WIDTH, HEIGHT, DPI, COLUMNS = 1200, 1656, 67, 4


def snapshot(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): sha256(path)
            for path in sorted(root.rglob("*")) if path.is_file()}


def written_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def source_state() -> dict:
    commit, dirty = git_state()
    return {"commit": commit, "dirty": dirty, "environment": environment(),
            "scripts": {"accept_content": sha256(Path(__file__).resolve()),
                        "tools/reproduce_pilot.py": sha256(ROOT / "tools/reproduce_pilot.py")}}


def bundled_inputs() -> dict:
    catalog = load_json(ROOT / "assets/catalog.json")
    texts = [asset for asset in catalog["assets"] if asset["kind"] == "text"]
    if (len(texts) != 3 or {a["metadata"].get("role") for a in texts}
            != {"body", "title", "advertisement"}
            or any(a["metadata"].get("historical_corpus") is not False for a in texts)):
        raise ValueError("Acceptance requires only the three bundled original demonstration texts")
    paths = {"assets/catalog.json", "profiles/identity.json", "profiles/controlled-v1.json"}
    for asset in catalog["assets"]:
        path = safe_path(ROOT, asset["path"])
        if sha256(path) != asset["sha256"]:
            raise ValueError(f"Bundled asset SHA differs: {asset['id']}")
        paths.add(asset["path"])
        paths.update(item["path"] for item in asset["metadata"].get("evidence_files", []))
        evidence = asset["rights"].get("evidence_uri")
        if evidence and "://" not in evidence:
            paths.add(evidence)
    for name in ("NOTICE.md", "CC0-1.0.txt"):
        relative = f"assets/texts/{name}"
        if (ROOT / relative).is_file():
            paths.add(relative)
    return {relative: sha256(safe_path(ROOT, relative)) for relative in sorted(paths)}


def composition(page: dict, *, geometry: bool = True) -> dict:
    value = {key: deepcopy(page[key]) for key in
             ("articles", "blocks", "lines", "words", "reading_order")}
    for collection in ("lines", "words"):
        for item in value[collection]:
            item.pop("legibility", None)
    if not geometry:
        for collection in ("blocks", "lines", "words"):
            for item in value[collection]:
                item.pop("polygon", None)
                item.pop("baseline", None)
        for article in value["articles"]:
            # The advert box bbox follows ink envelopes, legitimately different across sampling
            # factors; its frame (padding, rule_ids) stays in the signature.
            box = article.get("extensions", {}).get("mf:layout", {}).get("box")
            if isinstance(box, dict):
                box.pop("bbox", None)
    parameters = page["provenance"]["parameters"]
    value["text_spans"] = page["provenance"]["text_spans"]
    for key in ("layout", "layout_typography", "angle_degrees", "content_profile"):
        value[key] = parameters[key]
    return value


def unrotate(page: dict, points: list) -> list:
    angle = math.radians(page["provenance"]["parameters"]["angle_degrees"])
    c, s = math.cos(angle), math.sin(angle)
    cx, cy = page["image"]["width"] / 2, page["image"]["height"] / 2
    return [[c * (x - cx) - s * (y - cy) + cx, s * (x - cx) + c * (y - cy) + cy]
            for x, y in points]


def rendered_tokens(page: dict, span: dict) -> tuple[list[str], int]:
    """Reconstruct the displayed word fragments; do not trust reconstructed_text."""
    blocks = {item["id"]: item for item in page["blocks"]}
    lines = {item["id"]: item for item in page["lines"]}
    words = {item["id"]: item for item in page["words"]}
    tokens, pending, interblock_hyphens = [], None, 0
    for bid in span["block_ids"]:
        for lid in blocks[bid]["line_ids"]:
            for wid in lines[lid]["word_ids"]:
                word = words[wid]
                hyphen = word.get("hyphenation")
                if hyphen and hyphen["part"] == "start":
                    if pending is not None or not word["text"].endswith("-"):
                        raise ValueError(f"Invalid rendered hyphen start: {wid}")
                    pending = hyphen["group_id"], word["text"][:-1], bid
                elif hyphen and hyphen["part"] == "end":
                    if pending is None or pending[0] != hyphen["group_id"]:
                        raise ValueError(f"Invalid rendered hyphen continuation: {wid}")
                    tokens.append(pending[1] + word["text"])
                    interblock_hyphens += pending[2] != bid
                    pending = None
                else:
                    if pending is not None:
                        raise ValueError(f"Unclosed rendered hyphen before: {wid}")
                    tokens.append(word["text"])
    if pending is not None:
        raise ValueError("Unclosed rendered hyphen at source span end")
    return tokens, interblock_hyphens


class Acceptance:
    def __init__(self, root: Path, source: dict, inputs: dict):
        self.root, self.source, self.inputs = root, source, inputs
        self.profile_snapshot = None
        self.lot_snapshots = {}
        self.report = {
            "format": "mille-feuilles-content-acceptance", "version": "1", "status": "fail",
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "profile": PROFILE, "calibrated": False, "seed": SEED,
            "source": source, "inputs": inputs, "checks": [], "commands": [],
            "lots": {}, "sampling_comparisons": [], "errors": [],
            "scope": "Planned eight compact renders; bundled original texts only; no corpus or training evaluation",
            "visual_review": {"status": "not_run", "note": "Separate review required"},
            "historical_compatibility": {"status": "not_run", "note": "Separate proof against 178a79b"},
            "refusal_coverage": {
                "status": "not_run_here", "source_tests": ["tests/test_content.py",
                    "tests/test_content_render.py", "tests/test_content_pipeline.py",
                    "tests/test_content_validation.py"],
                "note": "Unit evidence covers invalid configuration, ineligible catalogs and partitions; no new import here",
            },
            "sampling_scope": "One body document; no frequency target or claim of multi-document uniformity from this campaign",
        }

    def check(self, condition: bool, description: str) -> None:
        if not condition:
            raise ValueError(description)
        self.report["checks"].append(description)

    def guard(self) -> None:
        self.check(source_state() == self.source, "Source revision, environment and scripts unchanged")
        self.check(bundled_inputs() == self.inputs, "Bundled original inputs unchanged")
        if self.profile_snapshot is not None:
            self.check(snapshot(self.root / "sources") == self.profile_snapshot,
                       "Prepared photometric profiles unchanged")
        for name, inventory in self.lot_snapshots.items():
            self.check(snapshot(self.root / f"lots/{name}") == inventory,
                       f"Completed lot remains unchanged: {name}")
        size = written_bytes(self.root)
        self.check(size <= MAX_BYTES, f"Volume {size} bytes within {MAX_BYTES} between commands")
        free = shutil.disk_usage(self.root).free
        self.check(free >= RESERVE_BYTES, f"Free disk reserve retained: {free} bytes")

    def run(self, name: str, arguments: list, *, script: Path | None = None) -> dict:
        self.guard()
        command = [sys.executable]
        command += [str(script)] if script else ["-m", "mille_feuilles.cli"]
        command += [str(arg) for arg in arguments]
        stdout, stderr = self.root / f"logs/{name}.json", self.root / f"logs/{name}.stderr.log"
        stdout.parent.mkdir(exist_ok=True)
        entry = {"name": name, "argv": command, "cwd": str(ROOT),
                 "stdout": str(stdout.relative_to(self.root)), "stderr": str(stderr.relative_to(self.root))}
        self.report["commands"].append(entry)
        print(f"Acceptation composition : {name}", file=sys.stderr, flush=True)
        started = time.perf_counter()
        with stdout.open("xb") as out, stderr.open("xb") as err:
            result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, check=False)
        entry.update(exit_code=result.returncode, elapsed_seconds=time.perf_counter() - started)
        self.guard()
        self.check(result.returncode == 0, f"{name}: CLI exit code zero")
        report = load_json(stdout)
        self.check(report.get("status") == "pass", f"{name}: command report passed")
        write_json(self.root / f"reports/{name}.json", report)
        return report

    def inspect_sources(self, name: str, target: Path, manifest: dict, pages: list[dict]) -> list:
        registry = {a["id"]: a for a in load_json(target / "assets.json")["assets"]}
        for relative, expected_sha in self.inputs.items():
            if relative.startswith("assets/"):
                self.check(sha256(safe_path(target, relative)) == expected_sha,
                           f"{name}/{relative}: bundled asset or evidence copied unchanged")
        texts, units, records = {}, {}, []
        for asset in sorted(registry.values(), key=lambda item: item["id"]):
            if asset["kind"] != "text" or asset["metadata"].get("role") != "body":
                continue
            path = safe_path(target, asset["path"])
            self.check(sha256(path) == asset["sha256"], f"{name}/{asset['id']}: copied body SHA")
            # The source index is Unicode after the same universal-newline rule.
            raw = path.read_text(encoding="utf-8")
            texts[asset["id"]] = raw
            units[asset["id"]] = text_units(raw, "body")
            count = len(units[asset["id"]])
            records.append({"asset_id": asset["id"], "source_document_id": asset["metadata"]["source_document_id"],
                            "sha256": asset["sha256"], "unit_count": count, "eligible": count >= 2,
                            "reason": None if count >= 2 else "fewer_than_two_body_units"})
        expected = {"version": "1", "profile": PROFILE, "calibrated": False, "documents": records}
        self.check(manifest["extensions"]["mf:content_profile"] == expected,
                   f"{name}: exact receipt recomputed for every copied body source")
        observations = []
        for page in pages:
            self.check(page["provenance"]["parameters"]["content_profile"] == PROFILE,
                       f"{name}/{page['page_id']}: explicit content profile")
            blocks = {block["id"]: block for block in page["blocks"]}
            templates = page["provenance"]["extensions"]["mf:template_article_ids"]
            spans = page["provenance"]["text_spans"]
            article_count = 0
            for article in page["articles"]:
                sequence = article.get("extensions", {}).get("mf:source_sequence")
                bodies = [bid for bid in article["block_ids"] if blocks[bid]["category"] == "texte"]
                if article["id"] in templates or not bodies:
                    self.check(sequence is None, f"{name}/{article['id']}: no sequence on template or advertisement")
                    continue
                self.check(sequence is not None, f"{name}/{article['id']}: body sequence exists")
                aid = sequence["asset_id"]
                self.check(aid in texts, f"{name}/{article['id']}: body uses one copied body document")
                first, last = sequence["unit_range"]
                self.check(0 <= first < last <= len(units[aid]) and last - first in (2, 3),
                           f"{name}/{article['id']}: two or three complete consecutive units")
                start, end = units[aid][first][1], units[aid][last - 1][2]
                self.check((sequence["start"], sequence["end"]) == (start, end),
                           f"{name}/{article['id']}: exact Unicode unit boundaries")
                owned = [span for span in spans if span["article_id"] == article["id"]
                         and registry[span["asset_id"]]["metadata"].get("role") == "body"]
                self.check(len(owned) == 1, f"{name}/{article['id']}: one source span owns the whole body")
                span = owned[0]
                self.check(span["block_ids"] == bodies and span["asset_id"] == aid
                           and (span["start"], span["end"]) == (start, end)
                           and span["source_document_id"] == registry[aid]["metadata"]["source_document_id"],
                           f"{name}/{article['id']}: span, article and document agree")
                tokens, interblock_hyphens = rendered_tokens(page, span)
                self.check(tokens == texts[aid][start:end].split(),
                           f"{name}/{article['id']}: all displayed fragments reconstruct the full source slice")
                observations.append({"page_id": page["page_id"], "article_id": article["id"],
                                     "asset_id": aid, "source_document_id": span["source_document_id"],
                                     "unit_range": [first, last], "unit_count": last - first,
                                     "start": start, "end": end, "body_blocks": len(bodies),
                                     "word_count": len(tokens), "interblock_hyphens": interblock_hyphens})
                article_count += 1
            self.check(article_count >= 1, f"{name}/{page['page_id']}: at least one committed multiunit body")
        return observations

    def generate(self, name: str, profile: Path, *, count: int, source: Path = ROOT, jobs: int = 1):
        target = self.root / f"lots/{name}"
        report = self.run(name, ["generate", "--output", target, "--assets-root", source,
                                "--pages", count, "--width", WIDTH, "--height", HEIGHT,
                                "--dpi", DPI, "--columns", COLUMNS, "--seed", SEED, "--jobs", jobs,
                                "--layout-profile", PROFILE_LAYOUT, "--content-profile", PROFILE,
                                "--degradation-profile", profile])
        self.check(all(check["status"] == "pass" for check in report["checks"]), f"{name}: all validation checks pass")
        manifest = load_json(target / "manifest.json")
        config = load_json(target / "config.json")
        self.check(config["render"]["content_profile"] == PROFILE, f"{name}: config activates content profile")
        self.check(manifest["profile"] == PROFILE_LAYOUT, f"{name}: layout profile remains v2")
        self.check(manifest["generator"]["commit"] == self.source["commit"] and not manifest["generator"]["dirty"],
                   f"{name}: clean production revision recorded")
        self.check(load_json(target / "environment.json") == self.source["environment"], f"{name}: frozen environment recorded")
        pages = [load_json(safe_path(target, entry["path"])) for entry in manifest["pages"]]
        self.check(len(pages) == count, f"{name}: expected page count")
        names = [check["name"] for check in report["checks"]]
        required = {"content_profile", "layout_profile", "degradation_profile", "exports", "export_inventory"}
        required |= {f"{kind}:{page['page_id']}" for page in pages for kind in ("page", "page_files")}
        self.check(len(names) == len(set(names)) and required <= set(names), f"{name}: named content/page/file/export checks")
        observations = self.inspect_sources(name, target, manifest, pages)
        recount = {"profile": PROFILE, "calibrated": False, "articles": len(observations),
                   "units_per_article": dict(sorted(Counter(str(item["unit_count"]) for item in observations).items())),
                   "body_documents": dict(sorted(Counter(item["source_document_id"] for item in observations).items()))}
        self.check(report["statistics"].get("content") == recount,
                   f"{name}: content statistics equal an independent recount of verified bodies")
        self.report["lots"][name] = {
            "path": str(target.relative_to(self.root)), "manifest_sha256": sha256(target / "manifest.json"),
            "pages": count, "observed_bodies": observations,
            "unit_counts": dict(sorted(Counter(str(item["unit_count"]) for item in observations).items())),
            "statistics": report["statistics"],
            "inventory": snapshot(target),
        }
        self.lot_snapshots[name] = self.report["lots"][name]["inventory"]
        return target, pages

    def compare_sampling(self, first: dict, second: dict) -> None:
        self.check(composition(first, geometry=False) == composition(second, geometry=False),
                   "Factor ×1/×2 preserves source selections, spans, identities, order, words, hyphens and layout")
        # zip() truncates silently: every paired sequence must have the same length first.
        self.check(len(first["lines"]) == len(second["lines"]) and len(first["words"]) == len(second["words"]),
                   "Factor ×1/×2 keeps line and word counts")
        self.check(all(len(a["baseline"]) == len(b["baseline"]) for a, b in zip(first["lines"], second["lines"])),
                   "Factor ×1/×2 keeps baseline point counts")
        self.check(all(len(a["polygon"]) == len(b["polygon"]) for a, b in zip(first["words"], second["words"])),
                   "Factor ×1/×2 keeps word polygon point counts")
        heights = [abs(a[1] - b[1]) for left, right in zip(first["lines"], second["lines"])
                   for a, b in zip(unrotate(first, left["baseline"]), unrotate(second, right["baseline"]))]
        self.check(bool(heights) and max(heights) <= 1e-5, "Factor ×1/×2 preserves native baseline heights within 1e-5 px")
        differences = [abs(a - b) for left, right in zip(first["words"], second["words"])
                       for pa, pb in zip(left["polygon"], right["polygon"]) for a, b in zip(pa, pb)]
        self.report["sampling_comparisons"].append({
            "page_id": first["page_id"], "max_native_baseline_height_difference_px": max(heights),
            "max_word_coordinate_difference_px": max(differences),
            "polygon_difference_threshold": None,
            "note": "Ink envelopes can differ across sampling factors; no identical-polygon claim",
        })

    def execute(self) -> None:
        profiles = {}
        for name, factor in (("identity", 1), ("identity", 2), ("controlled-v1", 1)):
            profile = deepcopy(load_profile(name))
            profile["oversampling"] = factor
            path = self.root / f"sources/{name}-x{factor}.json"
            write_json(path, profile)
            profiles[name, factor] = path
        self.profile_snapshot = snapshot(self.root / "sources")
        self.report["prepared_profiles"] = self.profile_snapshot
        original, pages = self.generate("identity-x1", profiles["identity", 1], count=2)
        original_inventory = snapshot(original)
        replay, _ = self.generate("replay-workers2", original / "provenance/degradation-profile.json",
                                  count=2, source=original, jobs=2)
        self.run("compare-replay", ["compare", original, replay])
        self.check(snapshot(replay) == original_inventory, "Every replay file is byte-identical with two workers")
        _, doubled = self.generate("identity-x2", profiles["identity", 2], count=1)
        controlled, changed = self.generate("controlled-x1", profiles["controlled-v1", 1], count=1)
        self.compare_sampling(pages[0], doubled[0])
        self.check(composition(pages[0]) == composition(changed[0]), "Photometry preserves complete composition and geometry")
        mask = pages[0]["extensions"]["mf:diagnostics"]["mask_path"]
        other_mask = changed[0]["extensions"]["mf:diagnostics"]["mask_path"]
        self.check((original / mask).read_bytes() == (controlled / other_mask).read_bytes(), "Photometry preserves the ideal mask")
        with Image.open(original / pages[0]["image"]["path"]) as a, Image.open(controlled / changed[0]["image"]["path"]) as b:
            self.check(a.convert("L").tobytes() != b.convert("L").tobytes(), "Controlled photometry changes decoded pixels")
        reproduced = self.root / "reproduced"
        report = self.run("reproduce", [original, "--output", reproduced,
                                       "--report", self.root / "reports/reproduction-detail.json"],
                          script=ROOT / "tools/reproduce_pilot.py")
        self.check(report["pages_reproduced"] == 2 and report["files_compared"] == 4,
                   "Reproduction verifies both PNG/canonical pairs")
        for page in pages:
            for relative in (page["image"]["path"], f"pages/{page['page_id']}.json",
                             page["extensions"]["mf:diagnostics"]["mask_path"],
                             page["extensions"]["mf:diagnostics"]["path"]):
                self.check((original / relative).read_bytes() == (reproduced / relative).read_bytes(),
                           f"Reproduction byte-identical: {relative}")
        self.check(snapshot(original) == original_inventory, "Original acceptance lot unchanged by replay and reproduction")
        self.report["reproduction"] = {"path": str(reproduced.relative_to(self.root)),
                                       "inventory": snapshot(reproduced),
                                       "scope": "PNG/canonical plus measured mask/diagnostics; no XML/COCO reproduction"}
        self.guard()
        self.report["status"] = "pass"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.expanduser().absolute()
    try:
        if root.exists() or root.is_symlink():
            raise ValueError(f"Destination already exists: {root}")
        resolved = root.resolve()
        if ROOT.resolve().is_relative_to(resolved):
            raise ValueError("Destination cannot contain the source repository")
        for name in ("assets", "profiles", "src", "schemas", "tools", "tests", "docs", ".git"):
            if resolved.is_relative_to((ROOT / name).resolve()):
                raise ValueError("Destination must be separate from frozen project inputs")
        if any((parent / "manifest.json").is_file() for parent in resolved.parents):
            raise ValueError("Destination cannot be nested inside a preserved dataset")
        ancestor = resolved.parent
        while not ancestor.exists():
            ancestor = ancestor.parent
        free = shutil.disk_usage(ancestor).free
        if free < RESERVE_BYTES + MAX_BYTES:
            raise ValueError(f"Need {RESERVE_BYTES + MAX_BYTES} free bytes including reserve; found {free}")
        source, inputs = source_state(), bundled_inputs()
        if source["dirty"]:
            raise ValueError("A clean committed source revision is required")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Refus : {exc}", file=sys.stderr)
        return 2
    root.mkdir(parents=True)
    acceptance = Acceptance(root, source, inputs)
    try:
        acceptance.execute()
    except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError, subprocess.CalledProcessError) as exc:
        acceptance.report["status"] = "fail"
        acceptance.report["errors"].append(f"{type(exc).__name__}: {exc}")
    # A failure must still perform the final freeze check without hiding its cause.
    try:
        acceptance.report["final_source"] = source_state()
        acceptance.report["final_inputs"] = bundled_inputs()
        acceptance.guard()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError) as exc:
        acceptance.report["status"] = "fail"
        acceptance.report["errors"].append(f"Final guard: {type(exc).__name__}: {exc}")
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    acceptance.report["resources"] = {
        "child_maxrss_raw": usage.ru_maxrss, "child_maxrss_unit": "bytes" if sys.platform == "darwin" else "KiB",
        "written_bytes_before_final_report": written_bytes(root), "limit_bytes": MAX_BYTES,
        "reserve_bytes": RESERVE_BYTES, "volume_scope": "Between commands and at finish; not an atomic subprocess quota",
    }
    output = root / "acceptance.json"
    write_json(output, acceptance.report)
    checksum = root / "acceptance.sha256"
    checksum.write_text(f"{hashlib.sha256(output.read_bytes()).hexdigest()}  acceptance.json\n", encoding="ascii")
    if written_bytes(root) > MAX_BYTES or shutil.disk_usage(root).free < RESERVE_BYTES:
        acceptance.report["status"] = "fail"
        acceptance.report["errors"].append("Final report exceeds volume budget or consumes reserved disk space")
        write_json(output, acceptance.report)
        checksum.write_text(f"{hashlib.sha256(output.read_bytes()).hexdigest()}  acceptance.json\n", encoding="ascii")
    print(json.dumps({"status": acceptance.report["status"], "path": str(output),
                      "visual_review": "not_run", "errors": acceptance.report["errors"]}, ensure_ascii=False))
    return 0 if acceptance.report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
