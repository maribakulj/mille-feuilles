"""Descriptive structural comparison of canonical pages with the cadrage's aggregated statistics.

The measurement definitions are those of ``tools/cadrage/calibrer.py`` itself: its pure functions
``mesurer`` and ``q`` are executed from the exact pinned bytes of that file, never re-read and never
via ``main``. Only ``calibration.json`` (aggregated) and canonical page JSON are inputs; no corpus is
opened. The result is a description, not a verdict of realism or of any gain (SPEC-A1 r2 + r2.1).
"""

from __future__ import annotations

import hashlib
import json
import types
from collections import defaultdict
from pathlib import Path

CALIBRER_SHA256 = "8b72e367424b6f8825539c46e349e2d948b942ff5412fd61a884fd4804ef820d"
CALIBRATION_SHA256 = "6349af2f15c39f0203ffdf873b07d07454a8a3671bab9ee28b5b637ecf731c08"
ENGINE_MODULE = "mille_feuilles._calibrer_cadrage"
REAL_COHORT_DEFAULT = "as:XIXe"
MF_SOURCE, MF_EPOCH = "mf", "XIXe"
TEXT_CATEGORIES = {"titre", "texte", "legende", "annonce", "autre"}
_STRUCT = {"titre": "heading", "legende": "caption"}
COUNT_INDICATORS = {"blocs_nombre", "blocs_surface", "ordre_transitions"}

# Indicators whose value is influenced by "texte" blocks (A propagated if any page has "autre").
TEXT_INFLUENCED = {
    "colonnes", "colonne_largeur_rel_W", "gouttiere_rel_W", "gouttieres_avec_filet_part",
    "ligne_hauteur_px_med_page", "ligne_hauteur_rel_H_med_page", "interligne_px_med_page",
    "interligne_rel_H_med_page", "largeur_colonne_sur_interligne", "caracteres_par_ligne_med_page",
    "cesure_fin_de_ligne_part", "titre_sur_texte_hauteur_ligne", "titre_ligne_sur_corps_texte",
}
STATUSES = ("C", "A", "NC", "ND")  # the only public statuses
_C = ("C", "même code, entrée équivalente", True)
_BANNER = ("A", "le bandeau Mille Feuilles est un article de gabarit ; inconnu côté AS "
           "(variante avec gabarit = protocole historique)", True)
_PX = ("A", "pixels non comparables entre résolutions : rapporté, comparaison interdite", False)
# name -> (definition status, reason, comparison allowed)
INDICATOR_STATUS: dict[str, tuple[str, str, bool]] = {
    **{name: _C for name in (
        "filets_par_page", "filets_verticaux_par_page", "filets_horizontaux_par_page",
        "filet_vertical_longueur_rel_H", "marge_gauche_rel_W", "marge_droite_rel_W", "marge_haut_rel_H",
        "marge_bas_rel_H", "zone_imprimee_largeur_rel_W", "page_rapport_H_sur_W", "colonnes",
        "colonne_largeur_rel_W", "gouttiere_rel_W", "gouttieres_avec_filet_part",
        "ligne_hauteur_rel_H_med_page", "interligne_rel_H_med_page", "largeur_colonne_sur_interligne",
        "caracteres_par_ligne_med_page", "cesure_fin_de_ligne_part", "titre_sur_texte_hauteur_ligne",
        "titre_ligne_sur_corps_texte", "ordre_transitions")},
    "ligne_hauteur_px_med_page": _PX,
    "interligne_px_med_page": _PX,
    **{name: _BANNER for name in (
        "articles_par_page", "article_lignes", "article_caracteres", "article_blocs",
        "article_colonnes_occupees", "article_contigu_dans_ordre", "article_avec_titre",
        "annonce_lignes", "annonce_caracteres", "annonce_blocs", "annonce_colonnes_occupees",
        "annonce_contigu_dans_ordre", "titre_largeur_en_colonnes", "titre_sur_plusieurs_colonnes")},
    "annonce_avec_titre": ("NC", "l'en-tête d'annonce MF est catégorisé annonce et non titre : 0 structurel", False),
    "blocs_nombre": ("A", "catégories canoniques retypées par D-231 ; réel annoté à la main", True),
    "blocs_surface": ("A", "catégories canoniques retypées par D-231 ; recouvrements comptés plusieurs fois", True),
    **{name: ("ND", "PrintSpace absent du canonique", False) for name in (
        "printspace_gauche_rel_W", "printspace_droite_rel_W", "printspace_haut_rel_H", "printspace_bas_rel_H")},
    **{name: ("ND", "dpi=None en v1 (unités physiques non mesurées)", False) for name in (
        "page_largeur_cm", "page_hauteur_cm", "colonne_largeur_cm", "gouttiere_mm",
        "interligne_pt_med_page", "ligne_hauteur_mm_med_page")},
    **{name: ("ND", "chemin des pages sans lignes (KB/BnF)", False) for name in (
        "interligne_estime_rel_H_med_page", "kb_groupes_ordonnes_par_page", "kb_blocs_par_groupe")},
}
_UNITS = {
    "colonne": ("colonne_largeur_rel_W", "colonne_largeur_cm"),
    "gouttière": ("gouttiere_rel_W", "gouttiere_mm"),
    "filet vertical": ("filet_vertical_longueur_rel_H",),
    "ligne de titre": ("titre_ligne_sur_corps_texte",),
    "titre rattaché à un article": ("titre_largeur_en_colonnes", "titre_sur_plusieurs_colonnes"),
    "groupe ordonné KB": ("kb_blocs_par_groupe",),
    "compte de blocs par catégorie": ("blocs_nombre",),
    "surface de blocs par catégorie": ("blocs_surface",),
    "compte de transitions d'ordre": ("ordre_transitions",),
}
SAMPLE_UNIT: dict[str, str] = {name: unit for unit, names in _UNITS.items() for name in names}


def sample_unit(name: str) -> str:
    if name in SAMPLE_UNIT:
        return SAMPLE_UNIT[name]
    if name.startswith("article_"):
        return "article"
    if name.startswith("annonce_"):
        return "annonce"
    return "page"


class RealismError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_engine(calibrer_path: Path) -> types.ModuleType:
    """Read calibrer.py once, check its SHA-256, execute exactly those bytes in a fresh module."""
    data = Path(calibrer_path).read_bytes()
    digest = _sha256(data)
    if digest != CALIBRER_SHA256:
        raise RealismError("sha_calibrer", f"SHA-256 {digest} ≠ {CALIBRER_SHA256}")
    module = types.ModuleType(ENGINE_MODULE)  # __name__ != "__main__": main() is never called
    code = compile(data, f"<calibrer.py sha256:{digest}>", "exec", dont_inherit=True)
    exec(code, module.__dict__)  # noqa: S102 - pinned bytes, pure definitions only
    return module


def load_reference(calibration_path: Path, cohort: str = REAL_COHORT_DEFAULT) -> dict:
    data = Path(calibration_path).read_bytes()
    digest = _sha256(data)
    if digest != CALIBRATION_SHA256:
        raise RealismError("calibration", f"SHA-256 {digest} ≠ {CALIBRATION_SHA256}")
    calibration = json.loads(data)
    if cohort not in calibration["stats"]:
        raise RealismError("cohort", f"cohorte absente : {cohort}")
    source, _, epoch = cohort.partition(":")
    pages = [p for p in calibration["pages"]
             if p["source"] == source and (not epoch or p["epoch"] == epoch)]
    columns_by_split: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for page in pages:
        columns_by_split[page["split"]][str(page["colonnes"])] += 1
    splits = sorted(columns_by_split, key=lambda name: (name != "train", name))
    population = (f"portent uniquement sur le split {splits[0]}" if len(splits) == 1
                  else f"regroupent {' et '.join(splits)}")
    return {
        "cohort": cohort, "calibration_sha256": digest, "stats": calibration["stats"][cohort],
        "pages": len(pages), "pages_by_split": {s: sum(v.values()) for s, v in sorted(columns_by_split.items())},
        "columns_by_split": {s: dict(sorted(v.items(), key=lambda kv: int(kv[0])))
                             for s, v in sorted(columns_by_split.items())},
        "note": f"Distributions de stats {population} ; seul l'histogramme des colonnes est séparable.",
    }


def template_article_ids(page: dict) -> list[str] | None:
    extensions = page.get("provenance", {}).get("extensions") or {}
    value = extensions.get("mf:template_article_ids")
    return list(value) if isinstance(value, list) else None


def canonical_to_pg(page: dict, *, include_template: bool = True) -> dict | None:
    """The structure calibrer.parse_page would yield for this page (native geometry, no rounding)."""
    templates = template_article_ids(page)
    if not include_template and templates is None:
        return None  # template identification unavailable: variant ND for this page
    skipped = set() if include_template else set(templates)
    lines = {line["id"]: line for line in page["lines"]}
    regions, kept = [], set()
    for block in page["blocks"]:
        category = block["category"]
        if category == "tableau":
            raise RealismError("table_block", f"bloc tableau non pris en charge en A1 : {block['id']}")
        if block.get("article_id") in skipped:
            continue
        kept.add(block["id"])
        if category in TEXT_CATEGORIES:
            region_lines = [{
                "poly": [list(p) for p in lines[lid]["polygon"]],
                "baseline": [list(p) for p in lines[lid]["baseline"]],
                "text": lines[lid]["text"], "article": block.get("article_id"),
            } for lid in block["line_ids"]]
            regions.append({"id": block["id"], "kind": "TextRegion", "struct": _STRUCT.get(category),
                            "poly": [list(p) for p in block["polygon"]], "lines": region_lines,
                            "text": "\n".join(line["text"] for line in region_lines)})
            if category == "annonce":
                regions.append({"id": f"{block['id']}__advert", "kind": "AdvertRegion", "struct": None,
                                "poly": [list(p) for p in block["polygon"]], "lines": [], "text": ""})
        elif category in ("separateur", "illustration"):
            kind = "SeparatorRegion" if category == "separateur" else "GraphicRegion"
            regions.append({"id": block["id"], "kind": kind, "struct": None,
                            "poly": [list(p) for p in block["polygon"]], "lines": [], "text": ""})
        else:
            raise RealismError("category", f"catégorie inconnue : {category}")
    order = [bid for bid in page["reading_order"]["block_ids"] if bid in kept]
    return {"width": page["image"]["width"], "height": page["image"]["height"], "regions": regions,
            "order": order, "groups": [order] if order else [], "printspace": None}


def measure_pages(pages: list[dict], engine: types.ModuleType, *, include_template: bool = True) -> dict:
    """Per-page calibrer measurements, accumulated as in calibrer.main; performs no I/O."""
    values: dict = defaultdict(lambda: defaultdict(list))
    counts: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    measured, excluded, has_autre = [], [], False
    for page in pages:
        pg = canonical_to_pg(page, include_template=include_template)
        if pg is None:
            excluded.append({"page_id": page["page_id"], "reason": "template_identification_unavailable"})
            continue
        # Only blocks kept in this variant count: an "autre" block of the removed template does not.
        skipped = set() if include_template else set(template_article_ids(page) or ())
        before = {b["id"]: b["category"] for b in page["blocks"]
                  if b.get("article_id") not in skipped}
        after = {b["id"]: b["category"] for b in engine.type_blocks(pg)}
        changes = []
        for bid in sorted(before.keys() | after.keys()):
            original, observed = before.get(bid), after.get(bid)
            expected = "texte" if original == "autre" else original
            if observed != expected:
                changes.append(f"{bid}: {original or 'absent'} → {observed or 'absent'}")
        if changes:
            # D-231 uses bounding boxes for cover. Even disjoint polygons can change a category
            # or suppress an illustration; accepting that would violate the equivalence matrix.
            raise RealismError("category_retyping", f"page {page['page_id']} : " + "; ".join(changes))
        has_autre = has_autre or any(b["category"] == "autre" and b.get("article_id") not in skipped
                                     for b in page["blocks"])
        engine.mesurer(pg, MF_SOURCE, None, values, counts, MF_EPOCH)  # dpi=None always in v1
        parameters = page.get("provenance", {}).get("parameters", {})
        measured.append({"page_id": page["page_id"], "profile": page.get("profile"),
                         "angle_degrees": parameters.get("angle_degrees"),
                         "oversampling": parameters.get("oversampling"),
                         "declared_dpi": page.get("image", {}).get("dpi"),
                         "columns_declared": parameters.get("columns")})
    return {"values": {k: list(v) for k, v in values[MF_SOURCE].items()},
            "counts": {k: dict(v) for k, v in counts[MF_SOURCE].items()},
            "pages": measured, "excluded": excluded, "has_autre": has_autre,
            "include_template": include_template}


def aggregate(measures: dict, engine: types.ModuleType) -> dict:
    """Same aggregation as calibrer.main (q for lists; valeur/part for counts); performs no I/O."""
    stats = {name: engine.q(v) for name, v in sorted(measures["values"].items())}
    for name, c in sorted(measures["counts"].items()):
        total = sum(c.values()) or 1
        stats[name] = {kk: {"valeur": round(vv, 4), "part": round(vv / total, 4)}
                       for kk, vv in sorted(c.items(), key=lambda t: -t[1])}
    return stats


def _position(mf: dict, real: dict) -> str:
    p50 = mf["p50"]
    if p50 < real["p10"]:
        return "< p10"
    if p50 > real["p90"]:
        return "> p90"
    return "p10–p90"


def definition_status(name: str, *, has_autre: bool) -> tuple[str, str, bool]:
    status, reason, allowed = INDICATOR_STATUS.get(name, ("ND", "indicateur hors de la matrice A1", False))
    if has_autre and name in TEXT_INFLUENCED and status == "C":
        return "A", "blocs autre lus comme texte par D-231 : métrique de texte influencée", allowed
    return status, reason, allowed


def compare(mf_stats: dict, real_stats: dict, *, has_autre: bool = False) -> dict:
    """Descriptive position of the MF median within the real p10–p90; never a verdict.

    Each entry keeps definition_status (from the matrix) and the effective status (ND when an
    observation is missing), comparison_allowed with its reason, the sample unit and the kind.
    """
    result = {}
    for name in sorted(set(INDICATOR_STATUS) | set(mf_stats) | set(real_stats)):
        defined, reason, allowed = definition_status(name, has_autre=has_autre)
        mf, real = mf_stats.get(name), real_stats.get(name)
        kind = "counts" if name in COUNT_INDICATORS else "distribution"
        entry = {"definition_status": defined, "status": defined, "reason": reason,
                 "comparison_allowed": allowed, "sample_unit": sample_unit(name), "kind": kind,
                 "mf": mf, "real": real}
        missing = mf is None or real is None or (kind == "distribution" and (mf.get("n") == 0 or real.get("n") == 0))
        if missing:
            entry.update(status="ND", comparison_allowed=False, position="non comparé",
                         reason=reason if defined == "ND" else "indicateur absent d'un côté (absence ≠ zéro)")
        elif not allowed:
            entry["position"] = "non comparé"
        elif kind == "counts":
            entry["position"] = "parts rapportées (comptes par catégorie, pas de quantiles)"
        elif "p10" not in mf or "p10" not in real:
            entry.update(comparison_allowed=False, position="non comparé (n = 1, sans p10/p90)")
        else:
            entry["position"] = _position(mf, real)
        result[name] = entry
    return result


def merge_measures(parts: list[dict]) -> dict:
    """Combine page-by-page measures exactly as one batch: concatenate values, sum counts."""
    values: dict = defaultdict(list)
    counts: dict = defaultdict(lambda: defaultdict(float))
    merged = {"pages": [], "excluded": [], "has_autre": False}
    for part in parts:
        for name, vals in part["values"].items():
            values[name].extend(vals)
        for name, cats in part["counts"].items():
            for cat, value in cats.items():
                counts[name][cat] += value
        merged["pages"] += part["pages"]
        merged["excluded"] += part["excluded"]
        merged["has_autre"] = merged["has_autre"] or part["has_autre"]
    merged.update(values={k: list(v) for k, v in values.items()}, counts={k: dict(v) for k, v in counts.items()})
    return merged


def build_report(pages: list[dict], engine: types.ModuleType, reference: dict) -> dict:
    """Exploratory helper (the CLI has its own file-based orchestration with the same statuses).

    avec_gabarit follows the historical protocol. sans_gabarit is a sensitivity analysis: if any page
    cannot identify its template, the variant is ND at cohort level; partial observations are kept with
    page IDs and exclusions, but no comparison is presented as the same sensitivity.
    """
    report = {"format": "mille-feuilles-realism-report", "version": "1",
              "scope": "Contrôle descriptif structurel ; aucun verdict de gain ni de réalisme global.",
              "calibrer_sha256": CALIBRER_SHA256, "reference": {k: v for k, v in reference.items() if k != "stats"},
              "variants": {}}
    for variant, include in (("avec_gabarit", True), ("sans_gabarit", False)):
        measures = measure_pages(pages, engine, include_template=include)
        stats = aggregate(measures, engine)
        entry = {"role": "protocole historique" if include else "analyse de sensibilité au bandeau",
                 "pages": measures["pages"], "excluded": measures["excluded"], "has_autre": measures["has_autre"]}
        if measures["excluded"]:
            entry.update(cohort_status="ND",
                         cohort_reason=f"identification du gabarit indisponible pour {len(measures['excluded'])} "
                                       f"page(s) sur {len(pages)} : comparaison neutralisée",
                         partial_observations=stats, comparison=None)
        else:
            entry.update(cohort_status="complete",
                         comparison=compare(stats, reference["stats"], has_autre=measures["has_autre"]))
        report["variants"][variant] = entry
    return report
