"""Auditable dataset assembly and visual quality-control artifacts."""

from __future__ import annotations

import importlib.metadata
import math
import platform
import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, features

from . import __version__
from .io import ROOT, sha256, write_json
from .render import Config, PROFILE, PROFILE_LAYOUT, PROFILE_MEASURED, SCHEMA_VERSION, render_page


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


def prepare_assets(
    root: Path, source: Path = ROOT, allowed_text_ids: set[str] | None = None,
    layout_profile: str | None = None,
) -> list[dict]:
    """Copy assets and their evidence, preserving the verified source catalog."""
    from .catalog import load_catalog, text_group, validate_catalog
    from .validation import safe_path

    if layout_profile not in (None, PROFILE_LAYOUT):
        raise ValueError("Profil de mise en page inconnu")
    template_id = "template_press_v2" if layout_profile else "template_press_v1"
    source = Path(source).resolve()
    catalog_path = safe_path(source, "assets/catalog.json")
    catalog = load_catalog(source)
    errors = validate_catalog(source, catalog)
    if errors:
        raise ValueError("Catalogue d'actifs invalide : " + "; ".join(errors[:5]))
    ids = [a["id"] for a in catalog["assets"]]
    if len(ids) != len(set(ids)) or {"template_press_v1", "template_press_v2"}.intersection(ids):
        raise ValueError("Identifiants d'actifs dupliqués ou identifiant de template réservé")
    for asset in catalog["assets"]:
        if asset["rights"]["status"] != "verified" or not asset["rights"]["redistribution_allowed"]:
            raise ValueError(f"Droits d'actif non résolus : {asset['id']}")
    if allowed_text_ids is not None:
        known = {a["id"] for a in catalog["assets"] if a["kind"] == "text"}
        if not allowed_text_ids or not allowed_text_ids.issubset(known):
            raise ValueError("Sélection de textes vide ou étrangère au catalogue")
        catalog = deepcopy(catalog)
        catalog["assets"] = [
            a for a in catalog["assets"] if a["kind"] != "text" or a["id"] in allowed_text_ids
        ]
        roles = {a["metadata"].get("role") for a in catalog["assets"] if a["kind"] == "text"}
        if not {"body", "title", "advertisement"}.issubset(roles):
            raise ValueError("La sélection doit contenir les trois rôles textuels")
    (root / "assets").mkdir(exist_ok=True)
    if allowed_text_ids is None:
        shutil.copyfile(catalog_path, root / "assets/catalog.json")
    else:
        write_json(root / "assets/catalog.json", catalog)
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
    template = {
        "id": template_id,
        "version": SCHEMA_VERSION,
        "profile": layout_profile or PROFILE,
        "heading": "MILLE FEUILLES",
        "subtitle": "Journal de démonstration — Édition synthétique",
        "layout": "masthead; article-by-article column flow; unordered rules",
        "source": "original demonstration template, not a historical facsimile",
    }
    if layout_profile:
        from .layout import DEFAULT_OPTIONS

        template.update({
            "layout": "masthead; main and optional lower column zones; wide headline; boxed ads",
            "layout_options": deepcopy(DEFAULT_OPTIONS),
            "calibrated": False,
        })
    write_json(template_path, template)
    assets = deepcopy(catalog["assets"])
    # New registries use explicit groups, including when the input was 0.2.0.
    for asset in assets:
        if asset["kind"] == "text":
            asset["metadata"]["source_group_id"] = text_group(asset)
            asset["metadata"].setdefault("language", "fr")
    assets += [
        {
            "id": template_id,
            "kind": "template",
            "path": "assets/template.json",
            "sha256": sha256(template_path),
            "source_uri": (
                f"urn:mille-feuilles:original-template:v{SCHEMA_VERSION}:{template_id}"
                if layout_profile else f"urn:mille-feuilles:original-template:v{SCHEMA_VERSION}"
            ),
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


def _select_partition(source: Path, name: str | None):
    """Return selected IDs and immutable plan/catalog metadata to carry forward."""
    from .partition import load_partition
    from .validation import load_json, safe_path, validate_partition_receipt

    manifest_path = source / "manifest.json"
    if manifest_path.is_file():
        manifest = load_json(manifest_path)
        if not isinstance(manifest, dict):
            raise ValueError("Manifeste source invalide")
        receipt = manifest.get("extensions", {}).get("mf:partition")
        if receipt is not None:
            if not isinstance(receipt, dict) or name != receipt.get("name"):
                raise ValueError("Réutiliser un lot partitionné exige sa même --partition")
            registry = load_json(safe_path(source, manifest["assets"]["path"]))
            errors = validate_partition_receipt(source, manifest, registry)
            if errors:
                raise ValueError("Reçu de partition source invalide : " + "; ".join(errors[:5]))
            plan_path = safe_path(source, receipt["path"])
            catalog_path = safe_path(source, receipt["source_catalog_path"])
            selected = set(load_json(plan_path)["partitions"][name])
            return selected, plan_path, catalog_path
    if name is None:
        if safe_path(source, "assets/partition.json").exists():
            raise ValueError(
                "Ce bundle possède un plan de partition : préciser --partition "
                "pour éviter de mélanger les sources train, dev et test"
            )
        return None, None, None
    selected = load_partition(source, name)
    if not selected:
        raise ValueError(f"La partition {name!r} est vide")
    return selected, safe_path(source, "assets/partition.json"), safe_path(source, "assets/catalog.json")


def preflight_content_profile(source: Path, profile: str, selected: set[str] | None = None) -> dict:
    """Check body eligibility only within the already selected text assets."""
    from .catalog import load_catalog
    from .content import preflight_content

    assets = [asset for asset in load_catalog(source)["assets"]
              if asset["kind"] == "text" and (selected is None or asset["id"] in selected)]
    return preflight_content(source, assets, profile=profile)


def content_statistics(pages: list[dict]) -> dict:
    """Count committed body sequences, cross-checked against their source spans."""
    from .content import PROFILE as CONTENT_PROFILE

    unit_counts, documents = Counter(), Counter()
    for page in pages:
        blocks = {block["id"]: block for block in page["blocks"]}
        for article in page["articles"]:
            sequence = article.get("extensions", {}).get("mf:source_sequence")
            if sequence is None:
                continue
            spans = [span for span in page["provenance"]["text_spans"]
                     if span["article_id"] == article["id"]
                     and all(span[key] == sequence[key] for key in ("asset_id", "start", "end"))]
            body_blocks = [identity for identity in article["block_ids"]
                           if blocks[identity]["category"] == "texte"]
            if (len(spans) != 1 or not body_blocks or spans[0]["block_ids"] != body_blocks
                    or not isinstance(spans[0].get("source_document_id"), str)
                    or not spans[0]["source_document_id"]):
                raise ValueError(f"Séquence de corps sans span exact : {article['id']}")
            first, last = sequence["unit_range"]
            if type(first) is not int or type(last) is not int or first < 0 or last - first not in (2, 3):
                raise ValueError(f"Nombre d'unités de corps invalide : {article['id']}")
            unit_counts[str(last - first)] += 1
            documents[spans[0]["source_document_id"]] += 1
    return {"profile": CONTENT_PROFILE, "calibrated": False,
            "articles": sum(unit_counts.values()), "units_per_article": dict(sorted(unit_counts.items())),
            "body_documents": dict(sorted(documents.items()))}


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


def contact_sheets(pages: list[dict], root: Path, prefix: str = "contact") -> None:
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
        sheet.save(root / "qa" / f"{prefix}_{offset // 10:02d}.jpg", quality=88)


def layout_statistics(pages: list[dict], layout_options: dict) -> dict:
    """Summarize observed layouts; line heights use rotated edge lengths in pixels."""
    layout_articles = [
        article["extensions"]["mf:layout"]
        for page in pages for article in page["articles"]
        if "mf:layout" in article.get("extensions", {})
    ]
    line_heights = {}
    for page in pages:
        block_zones = {
            block_id: article["extensions"]["mf:layout"]["zone_id"]
            for article in page["articles"]
            if "mf:layout" in article.get("extensions", {})
            for block_id in article["block_ids"]
        }
        for line in page["lines"]:
            zone_id = block_zones.get(line["block_id"])
            if zone_id is None:
                continue
            # Rotation preserves this edge length; an axis-aligned envelope
            # would spuriously grow with line width and page inclination.
            polygon = line["polygon"]
            height = math.hypot(
                polygon[3][0] - polygon[0][0], polygon[3][1] - polygon[0][1]
            )
            line_heights.setdefault(zone_id, Counter())[str(round(height))] += 1
    clamped_requests = sum(
        article["extensions"]["mf:layout"]["small_body_requested"]
        and round(page["provenance"]["parameters"]["layout_typography"][
            article["extensions"]["mf:layout"]["zone_id"]
        ]["normal_body_size"] * layout_options["small_body_ratio"]) < 10
        for page in pages for article in page["articles"]
        if "mf:layout" in article.get("extensions", {})
    )
    return {
        "profile": PROFILE_LAYOUT,
        "calibrated": False,
        "zones": dict(sorted(Counter(
            zone["id"] for page in pages
            for zone in page["provenance"]["parameters"]["layout"]["zones"]
        ).items())),
        "zone_columns": dict(sorted(Counter(
            f"{zone['id']}:{len(zone['columns'])}" for page in pages
            for zone in page["provenance"]["parameters"]["layout"]["zones"]
        ).items())),
        "wide_headlines": sum(item["headline"] is not None for item in layout_articles),
        "boxed_ads": sum(item["box"] is not None for item in layout_articles),
        "small_body_articles": sum(item["small_body"] for item in layout_articles),
        "small_body_requests": sum(item["small_body_requested"] for item in layout_articles),
        "small_body_clamped": clamped_requests,
        "small_body_inactive": sum(
            item["small_body_requested"] and not item["small_body"] for item in layout_articles
        ),
        "line_heights_px": {
            zone_id: dict(sorted(counts.items(), key=lambda item: int(item[0])))
            for zone_id, counts in sorted(line_heights.items())
        },
        "line_height_bin_px": 1,
        "body_sizes": dict(sorted(Counter(
            str(item["body_font_size"]) for item in layout_articles
        ).items())),
    }


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
    from .validation import load_json, validate_dataset, validate_page

    config = deepcopy(config)
    config.validate()
    if not 1 <= count <= 1000 or not 1 <= jobs <= 4:
        raise ValueError("Nombre de pages attendu : 1–1000 ; jobs : 1–4")
    source = Path(asset_source or ROOT).resolve()
    selected, plan_path, source_catalog_path = _select_partition(source, config.partition)
    content_receipt = (
        preflight_content_profile(source, config.content_profile, selected)
        if config.content_profile is not None else None
    )
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
    assets = prepare_assets(root, source, selected, layout_profile=config.layout_profile)
    receipt = None
    if plan_path is not None:
        (root / "provenance").mkdir()
        shutil.copyfile(plan_path, root / "provenance/partition.json")
        shutil.copyfile(source_catalog_path, root / "provenance/source-catalog.json")
        receipt = {
            "version": "1",
            "name": config.partition,
            "path": "provenance/partition.json",
            "sha256": sha256(root / "provenance/partition.json"),
            "source_catalog_path": "provenance/source-catalog.json",
            "source_catalog_sha256": sha256(root / "provenance/source-catalog.json"),
        }
    import_ref = None
    for relative in ("provenance/import-report.json", "assets/import-report.json"):
        report_source = source / relative
        if report_source.is_file():
            from .validation import safe_path

            target = root / "provenance/import-report.json"
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(safe_path(source, relative), target)
            import_ref = {"path": "provenance/import-report.json", "sha256": sha256(target)}
            break
    degradation_ref = None
    if config.degradation_profile is not None:
        profile_path = root / "provenance/degradation-profile.json"
        write_json(profile_path, config.degradation_profile)
        degradation_ref = {
            "path": "provenance/degradation-profile.json", "sha256": sha256(profile_path)
        }
    write_json(
        root / "config.json",
        {"schema_version": SCHEMA_VERSION, "render": config.as_dict(), "pages": count,
         **({"partition": receipt} if receipt else {})},
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
    if degradation_ref:
        diagnostics = [load_json(root / p["extensions"]["mf:diagnostics"]["path"]) for p in pages]
        counts = Counter(w["legibility"] for p in pages for w in p["words"])
        statistics["measured_degradations"] = {
            "profile": config.degradation_profile["name"],
            "calibrated": False,
            "legibility_method": "heuristic-v1",
            "legibility": {label: counts[label] for label in ("readable", "uncertain", "illegible")},
            "pages": [{"page_id": d["page_id"], **d["page"]} for d in diagnostics],
        }
        statistics["scope"] = (
            "synthetic measured degradations; heuristic labels, no calibrated realism or OCR gain"
        )
        by_id = {d["page_id"]: d["page"] for d in diagnostics}
        severe_first = sorted(pages, key=lambda p: (
            -by_id[p["page_id"]]["legibility"]["illegible"],
            -by_id[p["page_id"]]["legibility"]["uncertain"],
            by_id[p["page_id"]]["contrast"], p["page_id"],
        ))
        contact_sheets(severe_first, root, prefix="severity")
    if config.layout_profile:
        statistics["layout"] = layout_statistics(
            pages, load_json(root / "assets/template.json")["layout_options"]
        )
    if content_receipt is not None:
        statistics["content"] = content_statistics(pages)
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
    by_asset_id = {a["id"]: a for a in assets}
    dataset_id = f"mf_demo_{config.seed}_{count}"
    if degradation_ref:
        from .degrade import profile_sha256

        dataset_id += f"_measured_{profile_sha256(config.degradation_profile)[:12]}"
    if config.layout_profile:
        dataset_id += "_layout_v2"
    if receipt:
        dataset_id += f"_{config.partition}_{receipt['sha256'][:12]}"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "profile": config.layout_profile or (PROFILE_MEASURED if degradation_ref else PROFILE),
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
                    {by_asset_id[span["asset_id"]]["metadata"]["source_group_id"]
                     for span in p["provenance"]["text_spans"]}
                ),
            }
            for p in pages
        ],
        "artifacts": artifacts,
    }
    if receipt:
        manifest["extensions"] = {"mf:partition": receipt}
    if import_ref:
        manifest.setdefault("extensions", {})["mf:import_report"] = import_ref
    if degradation_ref:
        manifest.setdefault("extensions", {})["mf:degradation_profile"] = degradation_ref
    if content_receipt is not None:
        manifest.setdefault("extensions", {})["mf:content_profile"] = content_receipt
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
