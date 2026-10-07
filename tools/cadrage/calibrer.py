#!/usr/bin/env python3
"""Calibration du générateur sur les seules pages train/dev (docs/CADRAGE.md §1).

Bibliothèque standard seulement ; n'importe rien d'axel. Lit :

- le manifeste OLR de NewsEye AS (`newseye_as.json`) : pages `train` et `dev` ;
- le manifeste de segmentation d'axel (`seg/manifest.json`) : sources `kb`,
  `bnf`, `read`, pages `split == "train"` et `excluded is None` ;

puis les PAGE XML de ces pages, et l'en-tête (résolution) des images AS/READ.
Aucun fichier d'une page de test n'est ouvert : la liste des pages est
filtrée sur les manifestes **avant** toute ouverture, chaque ouverture passe
par `ouvrir()`, qui refuse une page de la liste d'exclusion et journalise le
chemin et son SHA-256 dans `fichiers_lus.tsv`.

Usage :
    python3 tools/cadrage/calibrer.py \
        --as-manifest ~/axel/data/prepared/olr/newseye_as.json \
        --seg-manifest ~/axel/data/prepared/seg/manifest.json \
        --out tools/cadrage/sortie
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import struct
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

Point = tuple[float, float]

# Pages de test connues d'axel (E12, `docs/e12.md` §1), refusées en dur en plus
# du filtre des manifestes. Les numéros AS de test sont ajoutés à l'exécution
# (lus dans le manifeste, sans ouvrir leurs fichiers).
E12_TEST = {
    "Ce-soir_7635415_D0000002", "Marianne_7644869_D0000002",
    "Paris-Soir_7636525_D0000002", "Regards_7635838_D0000005",
    "Regards_7639182_D0000004", "La_Presse_0513223_T0000003",
    "Le_Matin_0572776_T0000001", "L_OEuvre_4618409_T0000008",
    "Paris-Soir_7636525_D0000003", "Marianne_7644869_D0000003",
    "kb_00531072", "kb_00531073",
}
# Numéros (identifiants BnF) de ces pages : aucune page de ces numéros n'est lue.
E12_TEST_ISSUES = {"7635415", "7644869", "7636525", "7635838", "7639182",
                   "513223", "0513223", "572776", "0572776", "4618409", "04618409"}


class Journal:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str]] = []
        self.refus: set[str] = set()
        self.refus_issues: set[str] = set()

    def interdit(self, path: str, page: str, issue: str = "") -> str | None:
        stem = Path(path).stem
        if page in self.refus or stem in self.refus or (issue and issue in self.refus_issues):
            return f"page de test ou exclue ({page})"
        for iss in self.refus_issues:
            if re.search(rf"(^|[_-]){re.escape(iss)}([_-]|$)", stem):
                return f"porte un numéro de test ({iss})"
        return None

    def ouvrir(self, path: str, page: str, role: str, issue: str = "") -> bytes:
        why = self.interdit(path, page, issue)
        if why:
            raise SystemExit(f"REFUS : {path} : {why}")
        data = Path(path).read_bytes()
        self.rows.append((page, role, path, hashlib.sha256(data).hexdigest()))
        return data


# ---------------------------------------------------------------- PAGE XML

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _points(el: ET.Element | None) -> list[Point]:
    if el is None:
        return []
    pts = el.get("points")
    if pts:
        out = []
        for pair in pts.split():
            x, _, y = pair.partition(",")
            out.append((float(x), float(y)))
        return out
    return [(float(p.get("x", 0)), float(p.get("y", 0)))
            for p in el if _local(p.tag) == "Point"]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _text(el: ET.Element) -> str:
    te = _child(el, "TextEquiv")
    if te is None:
        return ""
    u = _child(te, "Unicode")
    return unicodedata.normalize("NFC", (u.text or "") if u is not None else "")


_ART = re.compile(r"structure\s*\{[^}]*?id:\s*([^;}\s]+)\s*;[^}]*type:\s*article")
_STRUCT = re.compile(r"structure\s*\{[^}]*type:\s*([A-Za-z-]+)")
_RO = re.compile(r"readingOrder\s*\{\s*index:\s*(\d+)")


def parse_page(data: bytes) -> dict:
    root = ET.fromstring(data)
    page = next(e for e in root.iter() if _local(e.tag) == "Page")
    out: dict = {"width": int(float(page.get("imageWidth", 0))),
                 "height": int(float(page.get("imageHeight", 0))),
                 "regions": [], "order": [], "groups": [], "printspace": None}
    ps = _child(page, "PrintSpace")
    if ps is not None:
        out["printspace"] = _points(_child(ps, "Coords"))
    for el in page.iter():
        kind = _local(el.tag)
        if not kind.endswith("Region") or el.get("id") is None:
            continue
        custom = el.get("custom", "")
        struct_ = el.get("type")
        for m in _STRUCT.finditer(custom):
            if m.group(1) != "article":
                struct_ = m.group(1)
        lines = []
        if kind == "TextRegion":
            raw = [c for c in el if _local(c.tag) == "TextLine"]
            ranked = []
            for k, ln in enumerate(raw):
                m = _RO.search(ln.get("custom", ""))
                ranked.append((int(m.group(1)) if m else k, k, ln))
            for _, _, ln in sorted(ranked, key=lambda t: (t[0], t[1])):
                ma = _ART.search(ln.get("custom", ""))
                lines.append({"poly": _points(_child(ln, "Coords")),
                              "baseline": _points(_child(ln, "Baseline")),
                              "text": _text(ln),
                              "article": ma.group(1) if ma else None})
        out["regions"].append({"id": el.get("id"), "kind": kind, "struct": struct_,
                               "poly": _points(_child(el, "Coords")),
                               "lines": lines, "text": _text(el)})
    # ordre : groupes ordonnés (KB : un groupe ≈ un article) puis aplati
    for og in page.iter():
        if _local(og.tag) != "OrderedGroup":
            continue
        refs = sorted(((int(r.get("index", 0)), r.get("regionRef"))
                       for r in og if _local(r.tag) == "RegionRefIndexed"),
                      key=lambda t: t[0])
        if refs:
            out["groups"].append([r for _, r in refs])
    seen: set[str] = set()
    for g in out["groups"]:
        for r in g:
            if r not in seen:
                seen.add(r)
                out["order"].append(r)
    return out


# ---------------------------------------------------------------- géométrie

def area(poly: list[Point]) -> float:
    s = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def bbox(poly: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def clip_rect(poly: list[Point], r: tuple[float, float, float, float]) -> list[Point]:
    """Sutherland–Hodgman contre un rectangle (exact si la couverture est un
    rectangle, ce qui est le cas des AdvertRegion/TableRegion lues)."""
    x0, y0, x1, y1 = r
    edges = [(lambda p: p[0] >= x0, lambda a, b: _ix(a, b, x0)),
             (lambda p: p[0] <= x1, lambda a, b: _ix(a, b, x1)),
             (lambda p: p[1] >= y0, lambda a, b: _iy(a, b, y0)),
             (lambda p: p[1] <= y1, lambda a, b: _iy(a, b, y1))]
    out = list(poly)
    for inside, inter in edges:
        if not out:
            break
        inp, out = out, []
        for i in range(len(inp)):
            cur, prev = inp[i], inp[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(inter(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(inter(prev, cur))
    return out


def _ix(a: Point, b: Point, x: float) -> Point:
    t = (x - a[0]) / (b[0] - a[0]) if b[0] != a[0] else 0.0
    return (x, a[1] + t * (b[1] - a[1]))


def _iy(a: Point, b: Point, y: float) -> Point:
    t = (y - a[1]) / (b[1] - a[1]) if b[1] != a[1] else 0.0
    return (a[0] + t * (b[0] - a[0]), y)


def covered(poly: list[Point], covers: list[list[Point]], half: float = 0.5) -> bool:
    a = area(poly)
    if a <= 0:
        return False
    return any(area(clip_rect(poly, bbox(c))) / a >= half for c in covers)


# ---------------------------------------------------------------- typage

def type_blocks(pg: dict) -> list[dict]:
    """Règle D-231 d'axel, réécrite : annonce si ≥ ½ dans une AdvertRegion,
    sinon tableau si ≥ ½ dans une TableRegion, sinon titre/légende/texte/autre ;
    illustration = région graphique couverte à moins de ½ par du texte ;
    TableRegion sans texte dedans = tableau ; SeparatorRegion = separateur."""
    R = [r for r in pg["regions"] if len(r["poly"]) >= 3]
    texts = [r for r in R if r["kind"] == "TextRegion"]
    adverts = [r["poly"] for r in R if r["kind"] == "AdvertRegion"]
    tables = [r for r in R if r["kind"] == "TableRegion"]
    graphics = [r for r in R if r["kind"] in ("GraphicRegion", "ImageRegion")]
    blocks = []
    for t in texts:
        s = (t["struct"] or "").lower()
        if adverts and covered(t["poly"], adverts):
            cat = "annonce"
        elif tables and covered(t["poly"], [x["poly"] for x in tables]):
            cat = "tableau"
        elif s == "heading":
            cat = "titre"
        elif s == "caption":
            cat = "legende"
        elif s in ("header", "footer", "page-number", "handwritten-annotation",
                   "marginalia", "signature-mark", "catch-word"):
            cat = "autre"
        else:
            cat = "texte"
        blocks.append({**t, "category": cat})
    tpolys = [t["poly"] for t in texts]
    for tb in tables:
        # une TableRegion doublée d'un bloc de texte (AS) n'est pas recomptée
        inner = sum(area(clip_rect(p, bbox(tb["poly"]))) for p in tpolys)
        if inner < 0.5 * max(area(tb["poly"]), 1):
            blocks.append({**tb, "category": "tableau"})
    for g in graphics:
        ga = area(g["poly"])
        inner = sum(area(clip_rect(g["poly"], bbox(p))) for p in tpolys)
        if ga > 0 and inner / ga < 0.5:
            blocks.append({**g, "category": "illustration"})
    for s in R:
        if s["kind"] == "SeparatorRegion":
            blocks.append({**s, "category": "separateur"})
    return blocks


# ---------------------------------------------------------------- mesures

def q(values: list[float]) -> dict:
    v = sorted(x for x in values if x == x)
    if not v:
        return {"n": 0}
    if len(v) == 1:
        return {"n": 1, "p50": round(v[0], 4)}
    qs = statistics.quantiles(v, n=20, method="inclusive")
    return {"n": len(v), "moy": round(statistics.fmean(v), 4),
            "p10": round(qs[1], 4), "p25": round(qs[4], 4), "p50": round(qs[9], 4),
            "p75": round(qs[14], 4), "p90": round(qs[17], 4),
            "min": round(v[0], 4), "max": round(v[-1], 4)}


def columns(items: list[tuple[float, float, float]], W: float) -> list[tuple[float, float]]:
    """Colonnes par regroupement des bords gauches des items étroits
    (x0, x1, poids) : groupes de bords à moins de 1,5 % de W l'un de l'autre,
    gardés s'ils pèsent ≥ 4 % du total, fusionnés s'ils sont à moins de 6 % de
    W (alinéas) ; largeur = 3e quartile des largeurs du groupe."""
    if not items:
        return []
    its = sorted(items)
    tot = sum(w for _, _, w in its) or 1.0
    groups: list[list[tuple[float, float, float]]] = [[its[0]]]
    for it in its[1:]:
        if it[0] - groups[-1][-1][0] <= 0.015 * W:
            groups[-1].append(it)
        else:
            groups.append([it])
    kept = [g for g in groups if sum(w for _, _, w in g) >= 0.04 * tot]
    merged: list[list[tuple[float, float, float]]] = []
    for g in kept:
        if merged and g[0][0] - merged[-1][0][0] < 0.06 * W:
            merged[-1].extend(g)
        else:
            merged.append(list(g))
    cols = []
    for g in merged:
        left = statistics.median(x0 for x0, _, _ in g)
        widths = sorted(x1 - x0 for x0, x1, _ in g)
        wq = widths[int(0.75 * (len(widths) - 1))]
        cols.append((left, left + wq))
    return cols


def col_index(x: float, cols: list[tuple[float, float]]) -> int:
    best, bd = -1, 1e18
    for k, (a, b) in enumerate(cols):
        d = 0 if a <= x <= b else min(abs(x - a), abs(x - b))
        if d < bd:
            best, bd = k, d
    return best


def baseline_y(ln: dict) -> float | None:
    b = ln["baseline"]
    if len(b) >= 2:
        return statistics.fmean(p[1] for p in b)
    if len(ln["poly"]) >= 3:
        return bbox(ln["poly"])[3]
    return None


HYPH = ("¬", "-", "⸗", "‐", "=")


def mesurer(pg: dict, src: str, dpi: float | None,
            M: dict[str, dict[str, list[float]]],
            C: dict[str, dict[str, dict[str, float]]], epoch: str) -> dict:
    """Mesures d'une page. `M` reçoit les valeurs (distributions), `C` les
    comptes par catégorie. `dpi` n'est utilisé que s'il vaut au moins 200
    (les JPEG AS à 96 dpi portent une résolution de métadonnée fausse)."""
    if dpi is not None and dpi < 200:
        dpi = None
    W, H = float(pg["width"]), float(pg["height"])
    blocks = type_blocks(pg)
    keys = [src, f"{src}:{epoch}"] if epoch else [src]
    res: dict = {}

    def add(name: str, v: float | None) -> None:
        if v is None:
            return
        for k in keys:
            M[k][name].append(v)

    def cnt(name: str, c: dict[str, float]) -> None:
        for k in keys:
            for kk, vv in c.items():
                C[k][name][kk] += vv

    # types de blocs : nombre et surface
    cnt("blocs_nombre", {k: float(v) for k, v in Counter(b["category"] for b in blocks).items()})
    surf: dict[str, float] = defaultdict(float)
    for b in blocks:
        surf[b["category"]] += area(b["poly"]) / (W * H)
    cnt("blocs_surface", surf)
    sep = [b for b in blocks if b["category"] == "separateur"]
    add("filets_par_page", len(sep))
    nv = nh = 0
    vlen = []
    for s in sep:
        x0, y0, x1, y1 = bbox(s["poly"])
        if (y1 - y0) > 3 * (x1 - x0):
            nv += 1
            vlen.append((y1 - y0) / H)
        elif (x1 - x0) > 3 * (y1 - y0):
            nh += 1
    add("filets_verticaux_par_page", nv)
    add("filets_horizontaux_par_page", nh)
    for v in vlen:
        add("filet_vertical_longueur_rel_H", v)

    # marges : enveloppe de toutes les régions, puis PrintSpace s'il existe
    allp = [p for b in blocks for p in b["poly"]]
    if allp:
        x0, y0, x1, y1 = bbox(allp)
        add("marge_gauche_rel_W", x0 / W)
        add("marge_droite_rel_W", (W - x1) / W)
        add("marge_haut_rel_H", y0 / H)
        add("marge_bas_rel_H", (H - y1) / H)
        add("zone_imprimee_largeur_rel_W", (x1 - x0) / W)
    if pg["printspace"]:
        x0, y0, x1, y1 = bbox(pg["printspace"])
        add("printspace_gauche_rel_W", x0 / W)
        add("printspace_droite_rel_W", (W - x1) / W)
        add("printspace_haut_rel_H", y0 / H)
        add("printspace_bas_rel_H", (H - y1) / H)
    add("page_rapport_H_sur_W", H / W)
    if dpi:
        add("page_largeur_cm", W / dpi * 2.54)
        add("page_hauteur_cm", H / dpi * 2.54)

    # colonnes : lignes de texte courant étroites (ou blocs, sans lignes)
    text_blocks = [b for b in blocks if b["category"] == "texte"]
    tx = [p for b in text_blocks for p in b["poly"]]
    pw = (bbox(tx)[2] - bbox(tx)[0]) if tx else W
    items = []
    body_lines = []
    for b in text_blocks:
        if b["lines"]:
            for ln in b["lines"]:
                if len(ln["poly"]) >= 3:
                    x0, y0, x1, y1 = bbox(ln["poly"])
                    body_lines.append((b, ln))
                    if (x1 - x0) <= 0.45 * pw:
                        items.append((x0, x1, y1 - y0))
        elif len(b["poly"]) >= 3:
            x0, y0, x1, y1 = bbox(b["poly"])
            if (x1 - x0) <= 0.45 * pw:
                items.append((x0, x1, y1 - y0))
    cols = columns(items, W)
    if not cols and text_blocks:
        # texte présent, aucune ligne étroite : une seule colonne pleine largeur
        cols = [(bbox(tx)[0], bbox(tx)[2])]
    add("colonnes", len(cols))
    for a, b_ in cols:
        add("colonne_largeur_rel_W", (b_ - a) / W)
        if dpi:
            add("colonne_largeur_cm", (b_ - a) / dpi * 2.54)
    gut = [cols[k + 1][0] - cols[k][1] for k in range(len(cols) - 1)]
    for g in gut:
        add("gouttiere_rel_W", g / W)
        if dpi:
            add("gouttiere_mm", g / dpi * 25.4)
    # gouttières garnies d'un filet vertical
    with_rule = 0
    for k in range(len(cols) - 1):
        a, b_ = cols[k][1], cols[k + 1][0]
        mid, half = (a + b_) / 2, max((b_ - a), 0.004 * W)
        if any(abs((bbox(s["poly"])[0] + bbox(s["poly"])[2]) / 2 - mid) <= half
               and (bbox(s["poly"])[3] - bbox(s["poly"])[1]) > 0.1 * H for s in sep):
            with_rule += 1
    if gut:
        add("gouttieres_avec_filet_part", with_rule / len(gut))
    res["colonnes"] = len(cols)

    # lignes : hauteur, pas, corps, caractères par ligne, césures
    heights, pitches, chars, hy = [], [], [], 0
    for b in text_blocks:
        prev = None
        for ln in b["lines"]:
            if len(ln["poly"]) < 3:
                continue
            x0, y0, x1, y1 = bbox(ln["poly"])
            heights.append(y1 - y0)
            t = ln["text"].strip()
            if t:
                chars.append(len(t))
                if t.endswith(HYPH):
                    hy += 1
            by = baseline_y(ln)
            if prev is not None and by is not None:
                d = by - prev[0]
                if d > 0 and abs(x0 - prev[1]) < 0.3 * (x1 - x0 + 1):
                    pitches.append(d)
            prev = (by, x0) if by is not None else None
    if heights:
        mh = statistics.median(heights)
        add("ligne_hauteur_px_med_page", mh)
        add("ligne_hauteur_rel_H_med_page", mh / H)
    if pitches:
        mp = statistics.median([p for p in pitches if p < 4 * statistics.median(pitches)])
        add("interligne_px_med_page", mp)
        add("interligne_rel_H_med_page", mp / H)
        if dpi:
            add("interligne_pt_med_page", mp / dpi * 72)
        if cols:
            add("largeur_colonne_sur_interligne", statistics.median(b - a for a, b in cols) / mp)
    if chars:
        add("caracteres_par_ligne_med_page", statistics.median(chars))
        add("cesure_fin_de_ligne_part", hy / len(chars))
    # KB/BnF : pas des lignes = hauteur du bloc / nombre de lignes du texte
    if not body_lines:
        est = []
        for b in text_blocks:
            n = len([x for x in b["text"].split("\n") if x.strip()])
            if n >= 3 and len(b["poly"]) >= 3:
                est.append((bbox(b["poly"])[3] - bbox(b["poly"])[1]) / n)
        if est:
            add("interligne_estime_rel_H_med_page", statistics.median(est) / H)
            ends = [x.strip() for b in text_blocks for x in b["text"].split("\n") if x.strip()]
            if ends:
                add("cesure_fin_de_ligne_part", sum(e.endswith(HYPH) for e in ends) / len(ends))
    # corps relatif des titres
    th = [bbox(ln["poly"])[3] - bbox(ln["poly"])[1]
          for b in blocks if b["category"] == "titre" for ln in b["lines"] if len(ln["poly"]) >= 3]
    if th and heights:
        add("titre_sur_texte_hauteur_ligne", statistics.median(th) / statistics.median(heights))
        for x in th:
            add("titre_ligne_sur_corps_texte", x / statistics.median(heights))
    if dpi and heights:
        add("ligne_hauteur_mm_med_page", statistics.median(heights) / dpi * 25.4)

    # articles et ordre (lignes à structure article : AS)
    by_id = {b["id"]: b for b in blocks}
    order = [r for r in pg["order"] if r in by_id and by_id[r]["category"] not in ("separateur",)]
    arts: dict[str, list[dict]] = defaultdict(list)
    for r in order:
        b = by_id[r]
        a = Counter(ln["article"] for ln in b["lines"] if ln["article"]).most_common(1)
        if a:
            arts[a[0][0]].append(b)
    if arts:
        add("articles_par_page", len(arts))
        pos = {r: i for i, r in enumerate(order)}
        mcw = statistics.median(b - a for a, b in cols) if cols else W / 4
        for aid, bl in arts.items():
            nlines = sum(len(b["lines"]) for b in bl)
            nchars = sum(len(ln["text"]) for b in bl for ln in b["lines"])
            cats = Counter(b["category"] for b in bl)
            kind = "annonce" if cats["annonce"] >= max(1, len(bl) / 2) else "article"
            add(f"{kind}_lignes", nlines)
            add(f"{kind}_caracteres", nchars)
            add(f"{kind}_blocs", len(bl))
            if cols:
                ci = {col_index((bbox(b["poly"])[0] + bbox(b["poly"])[2]) / 2, cols)
                      for b in bl if bbox(b["poly"])[2] - bbox(b["poly"])[0] < 1.5 * mcw}
                add(f"{kind}_colonnes_occupees", len(ci))
            idx = sorted(pos[b["id"]] for b in bl)
            add(f"{kind}_contigu_dans_ordre", 1.0 if idx[-1] - idx[0] + 1 == len(idx) else 0.0)
            tit = [b for b in bl if b["category"] == "titre"]
            add(f"{kind}_avec_titre", 1.0 if tit else 0.0)
            for t in tit:
                wt = (bbox(t["poly"])[2] - bbox(t["poly"])[0]) / mcw
                add("titre_largeur_en_colonnes", wt)
                add("titre_sur_plusieurs_colonnes", 1.0 if wt > 1.5 else 0.0)
    # transitions d'ordre de lecture entre blocs successifs (tous blocs ordonnés)
    seq = [by_id[r] for r in order if by_id[r]["category"] != "illustration"]
    if len(seq) >= 2:
        tr: Counter[str] = Counter()
        for p_, n_ in zip(seq, seq[1:]):
            a0, ay0, a1, ay1 = bbox(p_["poly"])
            b0, by0, b1, by1 = bbox(n_["poly"])
            ov = max(0.0, min(a1, b1) - max(a0, b0)) / max(1.0, min(a1 - a0, b1 - b0))
            if ov >= 0.5 and by0 >= ay1 - 0.01 * H:
                tr["dessous_meme_colonne"] += 1
            elif b0 >= a1 - 0.01 * W and by0 < ay0:
                tr["haut_colonne_suivante"] += 1
            elif b0 >= a1 - 0.01 * W:
                tr["a_droite_plus_bas"] += 1
            elif b1 <= a0 + 0.01 * W:
                tr["retour_a_gauche"] += 1
            elif ov >= 0.5:
                tr["remonte_meme_colonne"] += 1
            else:
                tr["autre"] += 1
        cnt("ordre_transitions", {k: float(v) for k, v in tr.items()})
    if pg["groups"] and src == "kb":
        add("kb_groupes_ordonnes_par_page", len(pg["groups"]))
        for g in pg["groups"]:
            add("kb_blocs_par_groupe", len(g))
    return res


# ---------------------------------------------------------------- résolution

def image_dpi(data: bytes) -> float | None:
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 4 < len(data):
            if data[i] != 0xFF:
                return None
            mk, ln = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
            if mk == 0xE0 and data[i + 4:i + 9] == b"JFIF\0":
                unit = data[i + 11]
                xd = struct.unpack(">H", data[i + 12:i + 14])[0]
                return float(xd) if unit == 1 else xd * 2.54 if unit == 2 else None
            i += 2 + ln
        return None
    if data[:2] in (b"II", b"MM"):
        e = "<" if data[:2] == b"II" else ">"
        off = struct.unpack(e + "I", data[4:8])[0]
        n = struct.unpack(e + "H", data[off:off + 2])[0]
        xres = unit = None
        for k in range(n):
            tag, typ, cnt_, val = struct.unpack(e + "HHII", data[off + 2 + 12 * k:off + 14 + 12 * k])
            if tag == 282 and typ == 5:
                num, den = struct.unpack(e + "II", data[val:val + 8])
                xres = num / den if den else None
            if tag == 296:
                unit = struct.unpack(e + "H", data[off + 10 + 12 * k:off + 12 + 12 * k])[0]
        if xres and unit == 3:
            return xres * 2.54
        return xres
    return None


def image_dpi_path(path: str) -> float | None:
    """Résolution d'un JPEG (JFIF) ou d'un TIFF, en ne lisant que l'en-tête
    (et, pour un TIFF, son premier répertoire d'étiquettes)."""
    with open(path, "rb") as f:
        head = f.read(1 << 16)
        if head[:2] in (b"II", b"MM"):
            e = "<" if head[:2] == b"II" else ">"
            off = struct.unpack(e + "I", head[4:8])[0]
            f.seek(off)
            n = struct.unpack(e + "H", f.read(2))[0]
            ifd = f.read(12 * n)
            xres = unit = None
            for k in range(n):
                tag, typ, _, val = struct.unpack(e + "HHII", ifd[12 * k:12 * k + 12])
                if tag == 282 and typ == 5:
                    f.seek(val)
                    num, den = struct.unpack(e + "II", f.read(8))
                    xres = num / den if den else None
                if tag == 296:
                    unit = struct.unpack(e + "H", ifd[12 * k + 8:12 * k + 10])[0]
            return xres * 2.54 if (xres and unit == 3) else xres
    return image_dpi(head)


# ---------------------------------------------------------------- principal

def main() -> int:
    ap = argparse.ArgumentParser()
    home = Path.home()
    ap.add_argument("--as-manifest", default=str(home / "axel/data/prepared/olr/newseye_as.json"))
    ap.add_argument("--seg-manifest", default=str(home / "axel/data/prepared/seg/manifest.json"))
    ap.add_argument("--out", default=str(Path(__file__).parent / "sortie"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    J = Journal()
    as_m = json.loads(J.ouvrir(a.as_manifest, "-", "manifeste"))
    seg_m = json.loads(J.ouvrir(a.seg_manifest, "-", "manifeste"))

    # 1. exclusions, d'après les manifestes seulement
    J.refus |= E12_TEST
    J.refus_issues |= E12_TEST_ISSUES
    for p in as_m["pages"]:
        if p["split"] not in ("train", "dev"):
            J.refus.add(p["page"])
            J.refus_issues.add(p["issue"])
            if p.get("read_page"):
                J.refus.add(p["read_page"])
    for p in seg_m["pages"]:
        if p["split"] != "train" or p.get("excluded") is not None:
            if p["source"] != "as":
                J.refus.add(p["page"])
                J.refus.add(Path(p["xml"]).stem)

    # 2. pages retenues
    todo = []
    for p in as_m["pages"]:
        if p["split"] in ("train", "dev"):
            todo.append(("as", p["page"], p["xml"], p.get("image"), p["issue"],
                         p["epoch"], p["split"], p["title"], p["date"]))
    for p in seg_m["pages"]:
        if p["source"] in ("kb", "bnf", "read") and p["split"] == "train" and p.get("excluded") is None:
            d = str(p.get("date") or "")
            ep = ""
            if d[:2] == "18" or d[:2] == "17":
                ep = "XIXe" if d[:2] == "18" else "XVIIIe"
            elif d[:2] == "19":
                ep = "XXe"
            todo.append((p["source"], p["page"], p["xml"], p.get("image"),
                         p.get("issue", ""), ep, "train", p.get("title") or "", d))

    M: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    C: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    pages_out = []
    ecartees = []
    for src, page, xml, img, issue, epoch, split, title, date in todo:
        iss = issue if src == "as" else ""
        why = J.interdit(xml, page, iss)
        if why:
            # même fichier ou même page qu'une page de test : écartée sans lecture
            ecartees.append({"page": page, "xml": xml, "raison": why})
            continue
        data = J.ouvrir(xml, page, "PAGE", iss)
        pg = parse_page(data)
        dpi = None
        if src in ("as", "read") and img and Path(img).exists():
            dpi = image_dpi_path(_head(J, img, page, iss))
        r = mesurer(pg, src, dpi, M, C, epoch)
        pages_out.append({"source": src, "page": page, "split": split, "epoch": epoch,
                          "title": title, "date": date, "dpi": dpi, **r})

    stats = {}
    for k in sorted(set(M) | set(C)):
        s: dict = {name: q(v) for name, v in sorted(M[k].items())}
        for name, c in sorted(C[k].items()):
            tot = sum(c.values()) or 1
            s[name] = {kk: {"valeur": round(vv, 4), "part": round(vv / tot, 4)}
                       for kk, vv in sorted(c.items(), key=lambda t: -t[1])}
        stats[k] = s
    col_hist: dict = defaultdict(Counter)
    for p in pages_out:
        col_hist[p["source"]][p["colonnes"]] += 1
        if p["epoch"]:
            col_hist[p["source"] + ":" + p["epoch"]][p["colonnes"]] += 1
    res = {"pages_par_source": dict(Counter(p["source"] for p in pages_out)),
           "pages_par_source_split_epoque": {f"{k[0]}:{k[1]}:{k[2]}": v for k, v in sorted(
               Counter((p["source"], p["split"], p["epoch"]) for p in pages_out).items())},
           "histogramme_colonnes": {k: dict(sorted(v.items())) for k, v in sorted(col_hist.items())},
           "ecartees_sans_lecture": ecartees,
           "stats": stats, "pages": pages_out}
    (out / "calibration.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    with (out / "fichiers_lus.tsv").open("w", encoding="utf-8") as f:
        f.write("page\trole\tchemin\tsha256\n")
        for row in J.rows:
            f.write("\t".join(row) + "\n")
    # contrôle final : aucune page lue n'est dans la liste d'exclusion
    lus = {r[0] for r in J.rows}
    assert not (lus & J.refus), lus & J.refus
    print(f"{len(pages_out)} pages, {len(J.rows)} fichiers lus, "
          f"{len(J.refus)} pages et {len(J.refus_issues)} numéros refusés")
    return 0


def _head(J: Journal, img: str, page: str, issue: str) -> str:
    """Contrôle et journalise l'image avant d'en lire l'en-tête."""
    Jrow_before = len(J.rows)
    stem = Path(img).stem
    if page in J.refus or stem in J.refus or (issue and issue in J.refus_issues):
        raise SystemExit(f"REFUS : {img}")
    J.rows.append((page, "en-tête image (résolution)", img, "-"))
    assert len(J.rows) == Jrow_before + 1
    return img


if __name__ == "__main__":
    sys.exit(main())
