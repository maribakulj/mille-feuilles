"""Auditable dataset assembly and visual quality-control artifacts."""

from __future__ import annotations

import importlib.metadata
import platform
import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, features

from . import __version__
from .io import ROOT, sha256, write_json
from .render import Config, PROFILE, SCHEMA_VERSION, render_page


def environment() -> dict:
    paths = sorted((ROOT / "src/mille_feuilles").glob("*.py"))
    paths += sorted((ROOT / "schemas").rglob("*.json"))
    paths += sorted((ROOT / "schemas").rglob("*.xsd"))
    paths += [ROOT / "uv.lock", ROOT / "pyproject.toml"]
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "implementation": platform.python_implementation(),
        "generator": __version__,
        "packages": {
            name: importlib.metadata.version(name)
            for name in ["Pillow", "numpy", "fonttools", "lxml", "jsonschema", "shapely"]
        },
        "freetype": features.version("freetype2"),
        "layout_engine": "pillow-freetype-basic",
        "sources": {str(p.relative_to(ROOT)): sha256(p) for p in paths if p.exists()},
    }


def git_state() -> tuple[str, bool]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Générer depuis le dépôt Git cloné pour conserver sa provenance"
        ) from exc
    return commit, dirty


def prepare_assets(root: Path, source: Path = ROOT) -> list[dict]:
    """Copy assets and their evidence, preserving the verified source catalog."""
    from jsonschema import Draft202012Validator
    from .validation import load_json, safe_path

    source = Path(source).resolve()
    catalog_path = safe_path(source, "assets/catalog.json")
    catalog = load_json(catalog_path)
    validator = Draft202012Validator(load_json(ROOT / "schemas/assets.schema.json"))
    errors = list(validator.iter_errors(catalog))
    if errors:
        raise ValueError(f"Catalogue d'actifs invalide : {errors[0].message}")
    ids = [a["id"] for a in catalog["assets"]]
    if len(ids) != len(set(ids)) or "template_press_v1" in ids:
        raise ValueError("Identifiants d'actifs dupliqués ou identifiant de template réservé")
    for asset in catalog["assets"]:
        if asset["rights"]["status"] != "verified" or not asset["rights"]["redistribution_allowed"]:
            raise ValueError(f"Droits d'actif non résolus : {asset['id']}")
    for role in ("body", "title", "advertisement"):
        candidates = [
            asset
            for asset in catalog["assets"]
            if asset["kind"] == "text" and asset["metadata"].get("role") == role
        ]
        if len(candidates) != 1:
            raise ValueError(f"Un seul actif texte requis pour le rôle {role}")
        content = safe_path(source, candidates[0]["path"]).read_text(encoding="utf-8")
        if not content.strip():
            raise ValueError(f"Texte vide pour le rôle {role}")
    (root / "assets").mkdir(exist_ok=True)
    shutil.copyfile(catalog_path, root / "assets/catalog.json")
    for asset in catalog["assets"]:
        evidence = asset["metadata"].get("evidence_files", [])
        if not isinstance(evidence, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("sha256"), str)
            for item in evidence
        ):
            raise ValueError(f"Liste de preuves invalide : {asset['id']}")
        records = [{"path": asset["path"], "sha256": asset["sha256"]}] + evidence
        evidence_uri = asset["rights"]["evidence_uri"]
        if not urlsplit(evidence_uri).scheme and evidence_uri not in {r["path"] for r in records}:
            records.append(
                {"path": evidence_uri, "sha256": sha256(safe_path(source, evidence_uri))}
            )
        for record in records:
            relative = record["path"]
            if not relative.startswith("assets/") or relative in {
                "assets/catalog.json",
                "assets/template.json",
                "assets/template-NOTICE.txt",
            }:
                raise ValueError(f"Chemin réservé ou hors du sous-dossier assets : {relative}")
            src = safe_path(source, relative)
            dst = safe_path(root, relative)
            if sha256(src) != record["sha256"]:
                raise ValueError(f"Empreinte source invalide : {relative}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    # Notices shared by original texts, not always listed as per-font evidence.
    for name in ["NOTICE.md", "CC0-1.0.txt"]:
        src = safe_path(source, f"assets/texts/{name}")
        if src.exists():
            (root / "assets/texts").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, root / "assets/texts" / name)
    template_path = root / "assets/template.json"
    template_notice = root / "assets/template-NOTICE.txt"
    template_notice.write_text(
        "Mille Feuilles: original demonstration layout and masthead strings, 2026-10-07.\n"
        "These template data are dedicated under CC0-1.0; not a historical facsimile.\n"
        "https://creativecommons.org/publicdomain/zero/1.0/\n",
        encoding="utf-8",
    )
    write_json(
        template_path,
        {
            "id": "template_press_v1",
            "version": SCHEMA_VERSION,
            "profile": PROFILE,
            "heading": "MILLE FEUILLES",
            "subtitle": "Journal de démonstration — Édition synthétique",
            "layout": "masthead; article-by-article column flow; unordered rules",
            "source": "original demonstration template, not a historical facsimile",
        },
    )
    assets = catalog["assets"] + [
        {
            "id": "template_press_v1",
            "kind": "template",
            "path": "assets/template.json",
            "sha256": sha256(template_path),
            "source_uri": "urn:mille-feuilles:original-template:v0.2",
            "rights": {
                "status": "verified",
                "license": "CC0-1.0",
                "evidence_uri": "assets/template-NOTICE.txt",
                "attribution": "Mille Feuilles",
                "redistribution_allowed": True,
            },
            "metadata": {
                "evidence_files": [
                    {"path": "assets/template-NOTICE.txt", "sha256": sha256(template_notice)}
                ],
                "literal_text": [
                    "MILLE FEUILLES",
                    "Journal de démonstration — Édition synthétique",
                ],
            },
        }
    ]
    write_json(root / "assets.json", {"schema_version": SCHEMA_VERSION, "assets": assets})
    return assets


def overlay(page: dict, root: Path) -> None:
    with Image.open(root / page["image"]["path"]) as src:
        canvas = src.convert("RGB")
    drawing = ImageDraw.Draw(canvas)
    for word in page["words"]:
        pts = [tuple(p) for p in word["polygon"]]
        drawing.line(pts + [pts[0]], fill=(190, 172, 230), width=1)
    for line in page["lines"]:
        pts = [tuple(p) for p in line["polygon"]]
        drawing.line(pts + [pts[0]], fill=(65, 171, 199), width=1)
        drawing.line([tuple(p) for p in line["baseline"]], fill=(15, 136, 194), width=1)
    colors = {
        "titre": (210, 60, 55),
        "texte": (44, 130, 73),
        "annonce": (214, 124, 26),
        "separateur": (75, 75, 75),
    }
    ranks = {identity: i for i, identity in enumerate(page["reading_order"]["block_ids"])}
    for block in page["blocks"]:
        pts = [tuple(p) for p in block["polygon"]]
        color = colors.get(block["category"], (145, 58, 178))
        drawing.line(pts + [pts[0]], fill=color, width=2)
        if block["id"] in ranks:
            drawing.text(
                pts[0],
                f"{block['id'].rsplit('_', 1)[-1]} / {ranks[block['id']]}",
                fill=color,
                stroke_width=1,
                stroke_fill="white",
            )
    drawing.text(
        (12, 12),
        f"{page['page_id']} | blocs/id/ordre, lignes, mots, baselines",
        fill=(0, 0, 0),
        stroke_width=1,
        stroke_fill="white",
    )
    canvas.thumbnail((1600, 2208))
    path = root / "qa" / f"{page['page_id']}.png"
    path.parent.mkdir(exist_ok=True)
    canvas.save(path, compress_level=6)


def contact_sheets(pages: list[dict], root: Path) -> None:
    for offset in range(0, len(pages), 10):
        chunk = pages[offset : offset + 10]
        sheet = Image.new(
            "RGB", (400 * min(5, len(chunk)), 580 * ((len(chunk) + 4) // 5)), "#ece8e0"
        )
        drawing = ImageDraw.Draw(sheet)
        for i, page in enumerate(chunk):
            with Image.open(root / page["image"]["path"]) as src:
                thumb = src.convert("RGB")
                thumb.thumbnail((380, 530))
            x, y = 400 * (i % 5), 580 * (i // 5)
            sheet.paste(thumb, (x + 10, y + 10))
            params = page["provenance"]["parameters"]
            drawing.text(
                (x + 12, y + 545),
                f"{page['page_id']} / {params['columns']} col. / {params['degradation']}",
                fill="black",
            )
        sheet.save(root / "qa" / f"contact_{offset // 10:02d}.jpg", quality=88)


def build_dataset(
    output: Path,
    config: Config,
    count: int = 1,
    jobs: int = 1,
    progress: Callable[[str], None] | None = None,
    asset_source: Path | None = None,
) -> dict:
    """Build, validate and leave a self-contained lot; never overwrite user files."""
    from .exports import export_coco, export_page
    from .validation import validate_dataset, validate_page

    config.validate()
    if not 1 <= count <= 1000 or not 1 <= jobs <= 4:
        raise ValueError("Nombre de pages attendu : 1–1000 ; jobs : 1–4")
    root = Path(output).absolute()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError(f"Destination non vide, aucune écriture : {root}")
    root.mkdir(parents=True, exist_ok=True)
    # Estimate PNG, annotation/XML, and QA space before writing any large image.
    estimated = count * config.width * config.height * 2.5 + 80_000_000
    if shutil.disk_usage(root).free < estimated + 500_000_000:
        raise ValueError(
            "Espace disque insuffisant pour ce lot ; réduire dimensions/nombre de pages"
        )
    assets = prepare_assets(root, asset_source or ROOT)
    write_json(
        root / "config.json",
        {"schema_version": SCHEMA_VERSION, "render": config.as_dict(), "pages": count},
    )
    write_json(root / "environment.json", environment())
    calibration_dir = root / "calibration"
    calibration_dir.mkdir()
    shutil.copyfile(ROOT / "docs/CADRAGE.md", calibration_dir / "CADRAGE.md")
    shutil.copyfile(
        ROOT / "tools/cadrage/sortie/fichiers_lus.tsv", calibration_dir / "fichiers_lus.tsv"
    )
    commit, dirty = git_state()
    pages = []

    def produce(index: int) -> dict:
        page = render_page(config, index, assets, root)
        issues = validate_page(page)
        if issues:
            raise ValueError(f"Page {index} invalide : " + "; ".join(issues[:10]))
        write_json(root / "pages" / f"{page['page_id']}.json", page)
        export_page(page, root)
        overlay(page, root)
        return page

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(produce, index): index for index in range(count)}
        try:
            for future in as_completed(futures):
                page = future.result()
                pages.append(page)
                if progress:
                    progress(
                        f"{len(pages)}/{count} pages : {page['page_id']}, {len(page['words'])} mots"
                    )
        except BaseException:
            # Running pages finish before the context manager exits. Pending
            # pages must not turn one failed export into a full failed campaign.
            for pending in futures:
                pending.cancel()
            raise
    pages.sort(key=lambda p: p["page_id"])
    export_coco(pages, root)
    contact_sheets(pages, root)
    statistics = {
        "pages": count,
        "words": sum(len(p["words"]) for p in pages),
        "lines": sum(len(p["lines"]) for p in pages),
        "blocks": sum(len(p["blocks"]) for p in pages),
        "columns": dict(
            sorted(Counter(str(p["provenance"]["parameters"]["columns"]) for p in pages).items())
        ),
        "degradations": dict(
            sorted(Counter(p["provenance"]["parameters"]["degradation"] for p in pages).items())
        ),
        "categories": dict(
            sorted(Counter(b["category"] for p in pages for b in p["blocks"]).items())
        ),
        "hyphenation_groups": sum(
            sum(w["hyphenation"] is not None for w in p["words"]) // 2 for p in pages
        ),
        "cross_block_articles": sum(
            sum(len(a["block_ids"]) > 1 for a in p["articles"]) for p in pages
        ),
        "scope": "synthetic demonstration / geometry QA; no evidence of OCR training gain",
    }
    write_json(root / "qa/statistics.json", statistics)
    artifacts = [
        {
            "path": str(path.relative_to(root)),
            "sha256": sha256(path),
            "role": path.relative_to(root).parts[0],
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": f"mf_demo_{config.seed}_{count}",
        "profile": PROFILE,
        "generator": {
            "commit": commit,
            "dirty": dirty,
            "environment_path": "environment.json",
            "environment_sha256": sha256(root / "environment.json"),
        },
        "config": {"path": "config.json", "sha256": sha256(root / "config.json")},
        "rng": {
            "algorithm": "SHA256 per-page; Python MT19937; numpy PCG64",
            "version": "1",
            "seed": config.seed,
        },
        "assets": {"path": "assets.json", "sha256": sha256(root / "assets.json")},
        "calibration": {
            "protocol_path": "calibration/CADRAGE.md",
            "protocol_sha256": sha256(calibration_dir / "CADRAGE.md"),
            "source_partitions": ["train", "dev"],
            "files_read": {
                "path": "calibration/fichiers_lus.tsv",
                "sha256": sha256(calibration_dir / "fichiers_lus.tsv"),
            },
        },
        "pages": [
            {
                "id": p["page_id"],
                "path": f"pages/{p['page_id']}.json",
                "sha256": sha256(root / "pages" / f"{p['page_id']}.json"),
                "source_group_ids": sorted(
                    {span["source_document_id"] for span in p["provenance"]["text_spans"]}
                ),
            }
            for p in pages
        ],
        "artifacts": artifacts,
    }
    write_json(root / "manifest.json", manifest)
    if progress:
        progress("Vérification du lot et des exports…")
    report = validate_dataset(root)
    report["statistics"] = statistics
    write_json(root / "qa/report.json", report)
    return report


def compare_lots(first: Path, second: Path) -> dict:
    """Compare the complete deterministic artifact inventory and manifest."""
    from .validation import load_json, safe_path, validate_dataset

    first, second = Path(first).resolve(), Path(second).resolve()
    issues = []
    for label, root in [("first", first), ("second", second)]:
        report = validate_dataset(root)
        issues.extend(f"{label}: {error}" for error in report["errors"])
    if issues:
        return {"status": "fail", "files_compared": 0, "mismatches": [], "errors": issues}
    one = load_json(first / "manifest.json")
    two = load_json(second / "manifest.json")
    files = {a["path"] for a in one["artifacts"]} | {a["path"] for a in two["artifacts"]}
    files.add("manifest.json")
    mismatches = [
        p
        for p in sorted(files)
        if not safe_path(first, p).is_file()
        or not safe_path(second, p).is_file()
        or sha256(safe_path(first, p)) != sha256(safe_path(second, p))
    ]
    return {
        "status": "fail" if mismatches else "pass",
        "files_compared": len(files),
        "mismatches": mismatches,
    }
