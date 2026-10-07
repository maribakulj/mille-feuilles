#!/usr/bin/env python3
"""Exercise partitioned CLI generation with original, explicitly excluded fixtures.

After committing and freezing the code, run in its locked environment:
  .venv/bin/python tools/accept_partitioned.py --output runs/accept-partitioned

The output must be new or empty and at least 650 MB must be free before it is
created. No file is removed, no production disk guard is overridden. All command
output and reports are retained, including failures. Exit codes: 0 acceptance
passed, 1 acceptance failed, 2 refusal before writing. The expected footprint is
less than 50 MB. reports/archive-index.json lists evidence for a future compact
archive; this script does not create an archive or assert protection against any
external corpus. All source texts and both exclusion examples are original.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata

from mille_feuilles.pipeline import environment


REPO = Path(__file__).resolve().parents[1]
ROLES = ("body", "title", "advertisement")
PARTITIONS = ("train", "dev", "test")
SEED = 20261009
MIN_FREE = 650_000_000
MAX_BYTES = 50_000_000


def ensure(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(content)


def write_json(path, value):
    write_new(path, json.dumps(value, ensure_ascii=False, sort_keys=True,
                               indent=2, allow_nan=False) + "\n")


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


def fixtures(root):
    """18 eligible documents, one excluded identity, one excluded original 8-gram."""
    source = root / "sources"
    write_new(source / "NOTICE.txt", (
        "Textes originaux pour l'acceptation Mille Feuilles, 2026-10-07.\n"
        "Ces textes synthétiques et les deux exemples exclus sont dédiés au domaine\n"
        "public sous CC0 1.0 Universal ; aucun corpus historique ou externe.\n"
        "https://creativecommons.org/publicdomain/zero/1.0/\n"
    ))
    rows = []

    def document(identity, group, role, content):
        relative = f"documents/{identity}.txt"
        write_new(source / relative, content + "\n")
        rows.append({
            "path": relative, "role": role, "source_document_id": identity,
            "source_group_id": group, "language": "fr", "date": "2026-10-07",
            "source_uri": f"urn:mille-feuilles:acceptance:{identity}",
            "content_type": "original_synthetic_demonstration", "historical_corpus": False,
            "rights": {
                "status": "verified", "license": "CC0-1.0", "evidence_path": "NOTICE.txt",
                "attribution": "Mille Feuilles original acceptance fixtures",
                "redistribution_allowed": True,
            },
        })

    for key, village in (("ambre", "Ambrelune"), ("azur", "Azurive"), ("cedre", "Cèdreclair")):
        for number in ("un", "deux"):
            contents = {
                "body": (
                    f"À {village}, Émile examine le dossier numéro {number}. "
                    "Les voisins dessinent un jardin près du pont et choisissent "
                    "les arbres du chemin. Une petite salle accueillera les lecteurs."
                ),
                "title": f"Les nouvelles de {village} : cahier {number}",
                "advertisement": (
                    f"Atelier de {village}, catalogue {number}. Livres reliés et "
                    "carnets solides sont proposés chaque matin près de la place."
                ),
            }
            for role, content in contents.items():
                document(f"original-{key}-{role}-{number}", f"group-{key}", role, content)
    rejected_id, rejected_ngram = "excluded-original-identity", "excluded-original-ngram"
    document(rejected_id, "excluded-group-identity", "body",
             "Les lanternes bleues du petit théâtre éclairent une maquette de bateau.")
    phrase = "Quatre lucioles inventent tranquillement des horloges sous verre"
    document(rejected_ngram, "excluded-group-ngram", "body", phrase + ".")
    write_new(source / "import.jsonl", "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    ))
    write_new(source / "excluded-documents.txt", rejected_id + "\n")
    words = re.findall(r"\w+", unicodedata.normalize("NFC", phrase).casefold())
    ensure(len(words) == 8, "The original exclusion phrase must contain exactly 8 words")
    salt = bytes.fromhex("102132435465768798a9bacbdcedfe0f")
    gram_hash = hashlib.sha256(salt + b"\x1f" + " ".join(words).encode()).hexdigest()[:32]
    write_json(source / "excluded-ngrams.json", {
        "format": "mille-feuilles-ngram-exclusions", "version": "1", "n": 8,
        "normalization": "nfc-casefold-word-v1", "salt_hex": salt.hex(),
        "digest": "sha256-128", "hashes": [gram_hash],
    })
    return source, rows, {rejected_id: "liste de documents", rejected_ngram: "n-gramme"}


class Acceptance:
    def __init__(self, root, frozen_environment):
        self.root = root
        self.frozen_environment = frozen_environment
        self.report = {
            "format": "mille-feuilles-partitioned-acceptance", "version": "1",
            "status": "fail", "seed": SEED, "commands": [], "checks": [], "errors": [],
            "scope": "Original synthetic fixtures; supplied exclusions only; no external corpus",
            "role_usage_note": "Observed documents are counted, never inferred from random selection.",
        }

    def check(self, condition, label):
        ensure(condition, label)
        self.report["checks"].append(label)

    def run(self, name, arguments, expected=0, script=None):
        command = [sys.executable]
        command += [str(script)] if script else ["-m", "mille_feuilles.cli"]
        command += [str(arg) for arg in arguments]
        print(f"Acceptation : {name}", file=sys.stderr, flush=True)
        result = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                                encoding="utf-8", check=False)
        stdout, stderr = f"logs/{name}.stdout.log", f"logs/{name}.stderr.log"
        write_new(self.root / stdout, result.stdout)
        write_new(self.root / stderr, result.stderr)
        record = {"name": name, "argv": command, "exit_code": result.returncode,
                  "expected_exit_code": expected, "stdout": stdout, "stderr": stderr}
        self.report["commands"].append(record)
        self.check(result.returncode == expected,
                   f"{name}: exit code {result.returncode}, expected {expected}")
        if expected:
            return result
        value = json.loads(result.stdout)
        record["report"] = f"reports/{name}.json"
        write_json(self.root / record["report"], value)
        self.check(value.get("status") == "pass", f"{name}: JSON report passed")
        return value

    def generate(self, name, destination, bundle, partition=None, jobs=1):
        args = ["generate", "--output", destination, "--assets-root", bundle,
                "--pages", 1, "--width", 800, "--height", 1100, "--columns", 4,
                "--degradation", "clean", "--jobs", jobs, "--seed", SEED]
        if partition is not None:
            args += ["--partition", partition]
        return self.run(name, args, expected=0 if partition else 2)

    def inspect_lot(self, label, root, partition, originals, selected, import_bytes):
        manifest = read_json(root / "manifest.json")
        self.check(read_json(root / "environment.json") == self.frozen_environment,
                   f"{label}: recorded environment equals the frozen preflight environment")
        registry = read_json(root / "assets.json")
        texts = {a["id"]: a for a in registry["assets"] if a["kind"] == "text"}
        self.check(set(texts) == selected, f"{label}: only selected text assets registered")
        retained = read_json(root / "assets/catalog.json")
        self.check({a["id"] for a in retained["assets"] if a["kind"] == "text"} == selected,
                   f"{label}: filtered catalog contains exactly selected text assets")
        inventory = {item["path"]: item["sha256"] for item in manifest["artifacts"]}
        reference = manifest["extensions"]["mf:import_report"]
        path = root / reference["path"]
        self.check(path.read_bytes() == import_bytes and
                   digest(path) == reference["sha256"] == inventory[reference["path"]],
                   f"{label}: import report preserved and inventoried")
        excluded = []
        for identity, (asset, content) in originals.items():
            if identity in selected:
                self.check((root / asset["path"]).read_bytes() == content,
                           f"{label}: selected bytes identical for {identity}")
            else:
                ensure(not (root / asset["path"]).exists(), f"{label}: excluded asset copied")
                excluded.append(content.strip())
        for path in root.rglob("*"):
            if path.is_file():
                value = path.read_bytes()
                ensure(all(content not in value for content in excluded),
                       f"{label}: excluded document bytes in {path.relative_to(root)}")
        self.check(True, f"{label}: no document bytes from other partitions copied")
        used, groups = defaultdict(set), set()
        ensure(len(manifest["pages"]) == 1, f"{label}: expected one page")
        for record in manifest["pages"]:
            page = read_json(root / record["path"])
            ensure(page["provenance"]["parameters"]["partition"] == partition,
                   f"{label}: page partition mismatch")
            page_groups = set()
            for span in page["provenance"]["text_spans"]:
                ensure(span["asset_id"] in selected, f"{label}: excluded source span")
                metadata = texts[span["asset_id"]]["metadata"]
                ensure(span["source_document_id"] == metadata["source_document_id"],
                       f"{label}: source document mismatch")
                used[metadata["role"]].add(span["source_document_id"])
                page_groups.add(metadata["source_group_id"])
            ensure(page_groups == set(record["source_group_ids"]),
                   f"{label}: manifest groups differ from actual used groups")
            groups.update(page_groups)
        self.check(True, f"{label}: used source documents and groups match the selected assets")
        return {
            "used_groups": sorted(groups),
            "roles": {role: {
                "available_documents": sum(a["metadata"]["role"] == role for a in texts.values()),
                "used_document_ids": sorted(used[role]), "used_documents": len(used[role]),
                "multiple_documents_observed": len(used[role]) > 1,
            } for role in ROLES},
        }

    def execute(self):
        code = code_snapshot()
        write_json(self.root / "reports/code.json", code)
        write_json(self.root / "reports/preflight-environment.json", self.frozen_environment)
        self.check(not code["dirty"], "Code was committed and clean before acceptance")
        source, rows, rejected = fixtures(self.root)
        original_snapshot = snapshot(source)
        write_json(self.root / "reports/original-source-sha256.json", original_snapshot)
        bundle = self.root / "bundle"
        imported = self.run("import", [
            "import-texts", "--manifest", source / "import.jsonl", "--into", bundle,
            "--exclude-documents", source / "excluded-documents.txt",
            "--exclude-ngrams", source / "excluded-ngrams.json",
        ])
        self.check(len(imported["accepted"]) == 18 and len(imported["rejected"]) == 2,
                   "Import accepted 18 documents and rejected 2")
        self.check({item["source_document_id"] for item in imported["rejected"]} == set(rejected),
                   "Both deliberately excluded original documents were rejected")
        for item in imported["rejected"]:
            ensure(any(rejected[item["source_document_id"]] in reason for reason in item["reasons"]),
                   "A fixture was rejected for a reason other than its intended exclusion")
        self.check(imported["external_protection"] == "evaluated" and all(
            value["status"] == "evaluated" for value in imported["exclusions"].values()
        ), "Both supplied synthetic exclusion lists were evaluated")
        planned = self.run("partition", ["partition", "--bundle", bundle,
                                         "--ratios", 1, 1, 1, "--seed", SEED])
        plan = planned["plan"]
        selected = {name: set(plan["partitions"][name]) for name in PARTITIONS}
        catalog = read_json(bundle / "assets/catalog.json")
        originals = {a["id"]: (a, (bundle / a["path"]).read_bytes())
                     for a in catalog["assets"] if a["kind"] == "text"}
        self.check(set.union(*selected.values()) == set(originals) and
                   sum(map(len, selected.values())) == len(originals) == 18,
                   "Three partitions cover 18 text assets without overlap")
        row_by_id = {row["source_document_id"]: row for row in rows}
        for asset, content in originals.values():
            row = row_by_id[asset["metadata"]["source_document_id"]]
            ensure(content == (source / row["path"]).read_bytes(), "Import changed original bytes")
        self.check(True, "Imported text bytes equal the original source documents")
        rejected_bytes = [(source / row_by_id[identity]["path"]).read_bytes().strip()
                          for identity in rejected]
        for path in bundle.rglob("*"):
            if path.is_file():
                ensure(all(content not in path.read_bytes() for content in rejected_bytes),
                       "An excluded original document was copied into the bundle")
        self.check(True, "Excluded original document bytes are absent from the imported bundle")
        source_groups, observed_characters = {}, {}
        for name, identities in selected.items():
            counts = Counter(originals[aid][0]["metadata"]["role"] for aid in identities)
            self.check(counts == {role: 2 for role in ROLES},
                       f"{name}: two available documents per role")
            source_groups[name] = {originals[aid][0]["metadata"]["source_group_id"] for aid in identities}
            observed_characters[name] = sum(len(originals[aid][1].decode("utf-8")) for aid in identities)
        self.check(len(set.union(*source_groups.values())) == 3 and
                   sum(map(len, source_groups.values())) == 3,
                   "Three source groups remain separate across partitions")
        self.check(plan["characters"] == observed_characters,
                   "Recorded partition characters equal actual Unicode lengths")
        self.report["requested_ratios"] = plan["ratios"]
        self.report["observed_source_characters"] = observed_characters
        bundle_snapshot = snapshot(bundle)
        forbidden = self.root / "forbidden-without-partition"
        refusal = self.generate("refuse-missing-partition", forbidden, bundle)
        self.check(not forbidden.exists() and "partition" in refusal.stderr.lower(),
                   "Missing partition refused with code 2 before destination creation")
        lots = {name: self.root / "lots" / name for name in PARTITIONS}
        for name, target in lots.items():
            self.generate(f"generate-{name}", target, bundle, name)
        replay = self.root / "lots/train-replay"
        train_before = snapshot(lots["train"])
        self.generate("replay-train", replay, lots["train"], "train", jobs=2)
        compared = self.run("compare-train-replay", ["compare", lots["train"], replay])
        self.check(compared["files_compared"] > 15 and not compared["mismatches"],
                   "Train and filtered-source replay are identical across the complete inventory")
        self.check(snapshot(replay) == train_before,
                   "All train and replay files are byte-identical, including the QA report")
        reproduced = self.run("reproduce-train", [
            lots["train"], "--output", self.root / "reproduced-train", "--report",
            self.root / "reports/reproduction-proof.json",
        ], script=REPO / "tools/reproduce_pilot.py")
        self.check(reproduced["pages_reproduced"] == 1 and reproduced["files_compared"] == 2
                   and not reproduced["mismatches"] and reproduced["environment"]["match"],
                   "Independent sequential reproduction matches the train image and page JSON")
        import_bytes = (bundle / "assets/import-report.json").read_bytes()
        usage = {name: self.inspect_lot(name, path, name, originals, selected[name], import_bytes)
                 for name, path in lots.items()}
        usage["train-replay"] = self.inspect_lot(
            "train-replay", replay, "train", originals, selected["train"], import_bytes)
        self.report["role_usage"] = usage
        groups = [set(usage[name]["used_groups"]) for name in PARTITIONS]
        self.check(all(groups) and sum(map(len, groups)) == len(set.union(*groups)),
                   "Actual page source groups are disjoint across train, dev and test")
        self.report["observed_documents_per_role"] = {
            role: sorted({identity for name in PARTITIONS
                          for identity in usage[name]["roles"][role]["used_document_ids"]})
            for role in ROLES
        }
        self.check(all(self.report["observed_documents_per_role"].values()),
                   "Every text role is represented by observed source spans")
        self.check(snapshot(source) == original_snapshot, "Original source SHA-256 values unchanged")
        self.check(snapshot(bundle) == bundle_snapshot, "Partitioned source bundle unchanged")
        self.check(snapshot(lots["train"]) == train_before, "Train lot unchanged by both reproductions")
        final_code = code_snapshot()
        write_json(self.root / "reports/final-code.json", final_code)
        self.check(final_code == code and not final_code["dirty"],
                   "Commit, clean Git state and both acceptance/reproduction script hashes unchanged")
        self.check(environment() == self.frozen_environment,
                   "Environment unchanged at the end of the acceptance campaign")
        self.report["counts"] = {"accepted_documents": 18, "rejected_documents": 2,
                                 "partition_pages": 3, "replay_pages": 1, "reproduced_pages": 1}
        self.report["status"] = "pass"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True, help="New or empty acceptance root")
    args = parser.parse_args(argv)
    root = args.output.absolute()
    try:
        ensure(not root.is_symlink(), "Output root must not be a symbolic link")
        ensure(not root.exists() or (root.is_dir() and not any(root.iterdir())),
               "Output is not empty; no file will be overwritten")
        parent = root
        while not parent.exists():
            parent = parent.parent
        available = shutil.disk_usage(parent).free
        ensure(available >= MIN_FREE,
               f"At least {MIN_FREE} free bytes required before writing; found {available}")
        frozen_environment = environment()
        root.mkdir(parents=True, exist_ok=True)
    except (OSError, RuntimeError) as exc:
        print(f"Refus : {exc}", file=sys.stderr)
        return 2
    acceptance = Acceptance(root, frozen_environment)
    acceptance.report["initial_free_bytes"] = available
    try:
        acceptance.execute()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        acceptance.report["status"] = "fail"
        acceptance.report["errors"].append(f"{type(exc).__name__}: {exc}")
    try:
        evidence = [
            {"path": p.relative_to(root).as_posix(), "sha256": digest(p), "bytes": p.stat().st_size}
            for p in sorted(root.rglob("*")) if p.is_file() and (
                p.relative_to(root).parts[0] in {"sources", "logs", "reports"}
                or p.name in {"manifest.json", "config.json", "assets.json", "environment.json",
                              "catalog.json", "import-report.json", "partition.json", "source-catalog.json"}
            )
        ]
        write_json(root / "reports/archive-index.json", {
            "format": "mille-feuilles-acceptance-evidence", "version": "1", "files": evidence,
            "include_also": ["acceptance.json", "reports/archive-index.json"],
            "scope": "Compact evidence only; generated images, XML and fonts remain in the full run.",
        })
        total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        acceptance.report["bytes_before_summary"] = total
        acceptance.check(total + len(json.dumps(acceptance.report, ensure_ascii=False,
                                               indent=2, sort_keys=True).encode()) + 1024
                         < MAX_BYTES, "Complete acceptance footprint is below 50 MB")
    except (OSError, ValueError, RuntimeError) as exc:
        acceptance.report["status"] = "fail"
        acceptance.report["errors"].append(f"{type(exc).__name__}: {exc}")
    try:
        write_json(root / "acceptance.json", acceptance.report)
    except OSError as exc:
        print(f"Rapport non écrit : {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": acceptance.report["status"], "report": str(root / "acceptance.json"),
                      "errors": acceptance.report["errors"]}, ensure_ascii=False))
    return 0 if acceptance.report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
