#!/usr/bin/env python3
"""Reproduce every PNG and canonical page JSON, sequentially, from an existing lot.

Run from the locked project environment, for example:
  .venv/bin/python tools/reproduce_pilot.py runs/pilot \
      --output runs/pilot-reproduced --report runs/reproduction.json

The destination must be new or empty. An optional report must be a new file
outside both lots. Generated copies are retained even on a mismatch. XML, COCO
and QA are not reproduced here. Exit status: 0 for exact reproduction, 1 for a
refusal, error or byte mismatch. No source file is changed.
"""

from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
import shutil
import sys
from typing import Callable

from mille_feuilles.io import sha256, write_json
from mille_feuilles.pipeline import environment, prepare_assets
from mille_feuilles.render import Config, SCHEMA_VERSION, render_page
from mille_feuilles.validation import load_json, safe_path, validate_partition_receipt


def checked_file(root: Path, relative: str, expected: str) -> Path:
    path = safe_path(root, relative)
    if not path.is_file():
        raise ValueError(f"Fichier source absent : {relative}")
    if sha256(path) != expected:
        raise ValueError(f"Empreinte source invalide : {relative}")
    return path


def same_bytes(left: Path, right: Path) -> bool:
    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as a, right.open("rb") as b:
        while True:
            first, second = a.read(1024 * 1024), b.read(1024 * 1024)
            if first != second:
                return False
            if not first:
                return True


def strict_config(value: dict) -> tuple[Config, int]:
    if not isinstance(value, dict) or set(value) not in (
        {"schema_version", "render", "pages"}, {"schema_version", "render", "pages", "partition"}
    ):
        raise ValueError("Structure de configuration inattendue")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Version de configuration incompatible")
    count = value["pages"]
    if type(count) is not int or not 1 <= count <= 1000:
        raise ValueError("Nombre de pages invalide dans la configuration")
    parameters = value["render"]
    expected = {field.name for field in fields(Config)}
    if not isinstance(parameters, dict) or set(parameters) != expected:
        raise ValueError("Paramètres de rendu incomplets ou inconnus")
    for name in ("width", "height", "dpi", "seed"):
        if type(parameters[name]) is not int:
            raise ValueError(f"Paramètre entier attendu : {name}")
    if parameters["columns"] is not None and type(parameters["columns"]) is not int:
        raise ValueError("Paramètre columns entier ou null attendu")
    if not isinstance(parameters["degradation"], str):
        raise ValueError("Paramètre degradation textuel attendu")
    config = Config(**parameters)
    config.validate()
    receipt = value.get("partition")
    if config.partition is not None and (
        not isinstance(receipt, dict) or receipt.get("name") != config.partition
    ):
        raise ValueError("Reçu de partition absent ou incohérent")
    if config.partition is None and receipt is not None:
        raise ValueError("Reçu de partition présent sans sélection")
    return config, count


def changed_fields(source: object, current: object, prefix: str = "") -> list[str]:
    if isinstance(source, dict) and isinstance(current, dict):
        differences = []
        for key in sorted(source.keys() | current.keys()):
            path = f"{prefix}.{key}" if prefix else key
            if key not in source or key not in current:
                differences.append(path)
            else:
                differences.extend(changed_fields(source[key], current[key], path))
        return differences
    return [] if source == current else [prefix]


def reproduce(
    root: Path,
    output: Path,
    report_path: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Keep all generated copies and return a report for both success and failure."""
    source = Path(root).resolve()
    target = Path(output).resolve()
    report = {
        "status": "fail",
        "scope": "all source PNG images and canonical page JSON; sequential render_page",
        "source_root": str(source),
        "output_root": str(target),
        "source_commit": None,
        "source_dirty": None,
        "source_manifest_sha256": None,
        "pages_expected": 0,
        "pages_reproduced": 0,
        "files_compared": 0,
        "mismatches": [],
        "errors": [],
        "environment": {"match": False, "differences": [], "source": None, "current": None},
        "space": {},
    }
    approved_report = None
    try:
        if report_path is not None:
            candidate = Path(report_path).resolve()
            if candidate.is_relative_to(source) or candidate.is_relative_to(target):
                raise ValueError("Le rapport doit être hors du lot source et du dossier reproduit")
            if candidate.exists():
                raise ValueError(f"Rapport déjà existant, aucune écriture : {candidate}")
            approved_report = candidate
        if not source.is_dir():
            raise ValueError(f"Lot source absent : {source}")
        if target.is_relative_to(source) or source.is_relative_to(target):
            raise ValueError(
                "Les lots source et reproduit doivent être dans des dossiers disjoints"
            )
        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise ValueError(f"Destination non vide, aucune écriture : {target}")

        manifest_path = safe_path(source, "manifest.json")
        manifest = load_json(manifest_path)
        report["source_manifest_sha256"] = sha256(manifest_path)
        if manifest["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Version de manifeste incompatible")
        generator = manifest["generator"]
        report["source_commit"] = generator["commit"]
        report["source_dirty"] = generator["dirty"]
        config_ref = manifest["config"]
        config_path = checked_file(source, config_ref["path"], config_ref["sha256"])
        config, count = strict_config(load_json(config_path))
        report["pages_expected"] = count
        env_path = checked_file(
            source, generator["environment_path"], generator["environment_sha256"]
        )
        recorded_env, current_env = load_json(env_path), environment()
        differences = changed_fields(recorded_env, current_env)
        report["environment"] = {
            "match": not differences,
            "differences": differences,
            "source": recorded_env,
            "current": current_env,
        }
        if differences:
            raise ValueError("Environnement différent avant génération : " + ", ".join(differences))

        registry_ref = manifest["assets"]
        registry_path = checked_file(source, registry_ref["path"], registry_ref["sha256"])
        selection_errors = validate_partition_receipt(source, manifest, load_json(registry_path))
        if selection_errors:
            raise ValueError("Reçu de sélection invalide : " + "; ".join(selection_errors[:5]))
        catalog_refs = [
            record for record in manifest["artifacts"] if record["path"] == "assets/catalog.json"
        ]
        if len(catalog_refs) != 1:
            raise ValueError("Le manifeste doit identifier une copie unique du catalogue source")
        checked_file(source, catalog_refs[0]["path"], catalog_refs[0]["sha256"])
        pages = manifest["pages"]
        if not isinstance(pages, list) or len(pages) != count:
            raise ValueError("Le nombre de pages diffère de la configuration")
        originals = []
        source_bytes = 0
        for index, reference in enumerate(pages):
            identity = f"mf_{index:04d}"
            if reference["id"] != identity or reference["path"] != f"pages/{identity}.json":
                raise ValueError(f"Index ou chemin canonique inattendu : {reference['id']}")
            page_path = checked_file(source, reference["path"], reference["sha256"])
            page = load_json(page_path)
            if page["page_id"] != identity or page["image"]["path"] != f"images/{identity}.png":
                raise ValueError(f"Identité ou image source incohérente : {identity}")
            image_path = checked_file(source, page["image"]["path"], page["image"]["sha256"])
            source_bytes += page_path.stat().st_size + image_path.stat().st_size
            originals.append((reference, page["image"], page_path, image_path))

        for folder, suffix in (("pages", ".json"), ("images", ".png")):
            expected_paths = {f"{folder}/mf_{index:04d}{suffix}" for index in range(count)}
            actual_paths = {
                path.relative_to(source).as_posix()
                for path in (source / folder).rglob(f"*{suffix}")
                if path.is_file()
            }
            if actual_paths != expected_paths:
                raise ValueError(
                    f"Inventaire {folder} différent du manifeste : "
                    + ", ".join(sorted(actual_paths ^ expected_paths))
                )

        disk_parent = target.parent
        while not disk_parent.exists():
            disk_parent = disk_parent.parent
        required = source_bytes + 500_000_000
        free = shutil.disk_usage(disk_parent).free
        report["space"] = {
            "original_images_and_json_bytes": source_bytes,
            "reserve_bytes": 500_000_000,
            "required_bytes": required,
            "available_bytes": free,
        }
        if free < required:
            raise ValueError(f"Espace libre insuffisant : {free} octets, {required} requis")

        target.mkdir(parents=True, exist_ok=True)
        assets = prepare_assets(target, source)
        if not same_bytes(registry_path, target / "assets.json"):
            raise ValueError("Le catalogue source ne reproduit pas le registre d'actifs du lot")
        for index, (reference, image_ref, page_path, image_path) in enumerate(originals):
            generated = render_page(config, index, assets, target)
            generated_page = target / f"pages/{generated['page_id']}.json"
            write_json(generated_page, generated)
            generated_image = safe_path(target, generated["image"]["path"])
            for kind, relative, expected_hash, original, reproduced in (
                ("page_json", reference["path"], reference["sha256"], page_path, generated_page),
                ("image_png", image_ref["path"], image_ref["sha256"], image_path, generated_image),
            ):
                original_hash, generated_hash = sha256(original), sha256(reproduced)
                byte_equal = same_bytes(original, reproduced)
                report["files_compared"] += 1
                if (
                    original_hash != expected_hash
                    or generated_hash != expected_hash
                    or not byte_equal
                ):
                    report["mismatches"].append(
                        {
                            "kind": kind,
                            "path": relative,
                            "expected_sha256": expected_hash,
                            "source_sha256": original_hash,
                            "generated_sha256": generated_hash,
                            "bytes_identical": byte_equal,
                        }
                    )
            report["pages_reproduced"] += 1
            if progress:
                progress(f"{index + 1}/{count} pages reproduites : {reference['id']}")
        if sha256(manifest_path) != report["source_manifest_sha256"]:
            raise ValueError("Le manifeste source a changé pendant la reproduction")
        if environment() != current_env:
            raise ValueError("L'environnement courant a changé pendant la reproduction")
        report["status"] = "fail" if report["mismatches"] else "pass"
    except (ValueError, OSError, KeyError, TypeError, IndexError, RuntimeError) as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["status"] = "fail"
    if approved_report is not None:
        try:
            # Exclusive creation also protects against an intervening writer.
            approved_report.parent.mkdir(parents=True, exist_ok=True)
            with approved_report.open("x", encoding="utf-8") as stream:
                json.dump(
                    report, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
                )
                stream.write("\n")
        except OSError as exc:
            report["errors"].append(f"Rapport non écrit : {exc}")
            report["status"] = "fail"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("root", type=Path, help="Lot source contenant manifest.json")
    parser.add_argument(
        "--output", type=Path, required=True, help="Dossier nouveau ou vide pour les copies"
    )
    parser.add_argument("--report", type=Path, help="Nouveau fichier JSON hors des deux lots")
    args = parser.parse_args(argv)
    report = reproduce(
        args.root,
        args.output,
        args.report,
        progress=lambda message: print(message, file=sys.stderr, flush=True),
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
