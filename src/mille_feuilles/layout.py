"""Declarative page plans for the v2 layout: column zones and wide headlines.

The planner is pure: it consumes the composition random stream passed by the
renderer in a fixed, documented order and returns plain data. It never draws,
measures fonts or reads files. Proportions are declared, not calibrated.

Two steps, because the body size (hence the masthead and the top of the content
area) depends on the main column width:
1. draw_layout: every random draw and the horizontal geometry;
2. place_zones: deterministic vertical placement once the content top is known.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from copy import deepcopy

LAYOUT_VERSION = "1"
MIN_BODY_PX = 10
ZONE_IDS = ("main", "rez_de_chaussee")
RULE_PX = 2
PAGE_LIMITS = (100, 20000)          # pixels, bornes de largeur et de hauteur acceptées
PLAN_KEYS = {"version", "width", "height", "margin", "gutter", "zones", "zone_rules",
             "rez_de_chaussee_share", "min_zone_height"}
ZONE_KEYS = {"id", "bbox", "columns", "headline_span", "headline_reserved", "headline_body_band"}
DEFAULT_OPTIONS = {
    "main_columns": {"choice": [4, 5, 6], "weights": [1, 3, 6]},
    "rez_de_chaussee_probability": 0.5,
    "rez_de_chaussee_share": [0.20, 0.35],
    "rez_de_chaussee_columns": {"choice": [3, 4, 5, 6], "weights": [1, 2, 2, 1]},
    "headline_probability": 0.4,
    "headline_span": {"choice": [2, 3], "weights": [2, 1]},
    "small_body_ratio": 0.82,
    "small_body_probability": {"body": 0.15, "advertisement": 0.6},
    "boxed_ad_probability": 0.3,
    "box_padding_px": [3, 6],
    "zone_gap_px": 8,
}


class LayoutError(ValueError):
    """A layout option set or plan that cannot be used."""


def _number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _choice(options: dict, key: str, low: int, high: int) -> None:
    value = options[key]
    if not isinstance(value, dict) or set(value) != {"choice", "weights"}:
        raise LayoutError(f"{key} : objet {{choice, weights}} attendu")
    choice, weights = value["choice"], value["weights"]
    if not isinstance(choice, list) or not isinstance(weights, list) or not choice or len(choice) != len(weights):
        raise LayoutError(f"{key} : listes choice/weights non vides et de même longueur")
    if any(isinstance(c, bool) or not isinstance(c, int) or not low <= c <= high for c in choice):
        raise LayoutError(f"{key} : entiers dans {low}..{high} attendus")
    if len(set(choice)) != len(choice):
        raise LayoutError(f"{key} : choix dupliqués")
    if any(not _number(w) or w <= 0 for w in weights):
        raise LayoutError(f"{key} : poids finis strictement positifs attendus")
    try:
        total = math.fsum(float(w) for w in weights)
    except OverflowError:
        total = math.inf
    if not math.isfinite(total):
        raise LayoutError(f"{key} : somme des poids non finie")


def _probability(value, key: str) -> None:
    if not _number(value) or not 0 <= value <= 1:
        raise LayoutError(f"{key} : probabilité dans [0, 1] attendue")


def _interval(value, key: str, low: float, high: float, integer: bool = False) -> None:
    if (
        not isinstance(value, list) or len(value) != 2 or not all(_number(v) for v in value)
        or (integer and any(isinstance(v, float) for v in value))
        or not low <= value[0] <= value[1] <= high
    ):
        raise LayoutError(f"{key} : intervalle ordonné dans [{low}, {high}] attendu")


def check_options(options: dict) -> dict:
    """Validate declared layout options; return them unchanged."""
    if not isinstance(options, dict) or set(options) != set(DEFAULT_OPTIONS):
        raise LayoutError("Options de mise en page : clés attendues " + ", ".join(sorted(DEFAULT_OPTIONS)))
    _choice(options, "main_columns", 2, 6)
    _choice(options, "rez_de_chaussee_columns", 2, 6)
    _choice(options, "headline_span", 2, 5)
    for key in ("rez_de_chaussee_probability", "headline_probability", "boxed_ad_probability"):
        _probability(options[key], key)
    _interval(options["rez_de_chaussee_share"], "rez_de_chaussee_share", 0.05, 0.6)
    _interval(options["box_padding_px"], "box_padding_px", 1, 20, integer=True)
    ratio = options["small_body_ratio"]
    if not _number(ratio) or not 0.6 <= ratio <= 1:
        raise LayoutError("small_body_ratio : nombre dans [0.6, 1] attendu")
    small = options["small_body_probability"]
    if not isinstance(small, dict) or set(small) != {"body", "advertisement"}:
        raise LayoutError("small_body_probability : clés body et advertisement attendues")
    for role, value in small.items():
        _probability(value, f"small_body_probability.{role}")
    gap = options["zone_gap_px"]
    if isinstance(gap, bool) or not isinstance(gap, int) or not 4 <= gap <= 64:
        raise LayoutError("zone_gap_px : entier dans 4..64 attendu")
    return options


def _columns(count: int, width: int, margin: int, gutter: float) -> tuple[float, list[list[float]]]:
    col_w = (width - 2 * margin - (count - 1) * gutter) / count
    return col_w, [
        [round(margin + i * (col_w + gutter), 6), round(margin + i * (col_w + gutter) + col_w, 6)]
        for i in range(count)
    ]


def _column_width(count: int, width: int, margin: int, gutter: float) -> float:
    """Width of one column exactly as recorded in the plan (rounded coordinates)."""
    x0, x1 = _columns(count, width, margin, gutter)[1][0]
    return x1 - x0


def _draw_columns(rng: random.Random, spec: dict, width: int, margin: int, gutter: float,
                  column_ok: Callable[[float], bool], label: str, exclude: int | None = None) -> int:
    allowed = [
        (count, weight) for count, weight in zip(spec["choice"], spec["weights"])
        if count != exclude
        and _columns(count, width, margin, gutter)[0] > 0 and column_ok(_columns(count, width, margin, gutter)[0])
    ]
    if not allowed:
        raise LayoutError(f"{label} : aucune option de colonnes ne tient à cette largeur")
    counts, weights = zip(*allowed)
    return rng.choices(list(counts), list(weights))[0]


def draw_layout(rng: random.Random, options: dict, *, width: int, height: int, margin: int, gutter: float,
                column_ok: Callable[[float], bool],
                rdc_column_ok: Callable[[float, float], bool] | None = None) -> dict:
    """All random choices of the v2 layout, in a fixed order, plus horizontal geometry.

    Order of draws: 1 main columns; 2 rez-de-chaussée yes/no; 3 if yes: share,
    then its columns (always different from the main count); 4 headline yes/no;
    5 if yes: span. The gutter and body ratio are drawn by the renderer before.

    The rez-de-chaussée shares the body size of main. rdc_column_ok(candidate,
    main_width) therefore receives the drawn main column width (as recorded in
    the plan) to derive its fonts; without it, column_ok(candidate) is used.
    Neither callback consumes the random stream, so draws are unchanged.
    """
    check_options(options)
    if not isinstance(rng, random.Random):
        raise LayoutError("Un random.Random est attendu (flux de composition)")
    for name, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int) or not PAGE_LIMITS[0] <= value <= PAGE_LIMITS[1]:
            raise LayoutError(f"{name} : entier dans {PAGE_LIMITS[0]}..{PAGE_LIMITS[1]} attendu")
    if isinstance(margin, bool) or not isinstance(margin, int) or not 0 <= margin < height / 2:
        raise LayoutError("Marge invalide pour la hauteur de page")
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0 or \
            isinstance(margin, bool) or not isinstance(margin, int) or not 0 <= margin < width / 2 or \
            not _number(gutter) or gutter < 0:
        raise LayoutError("Largeur, marge ou gouttière invalides")
    main = _draw_columns(rng, options["main_columns"], width, margin, gutter, column_ok, "main_columns")
    share = rdc = None
    if rng.random() < options["rez_de_chaussee_probability"]:
        share = rng.uniform(*options["rez_de_chaussee_share"])
        if rdc_column_ok is None:
            rdc_ok = column_ok
        else:
            main_width = _column_width(main, width, margin, gutter)

            def rdc_ok(candidate: float) -> bool:
                return rdc_column_ok(candidate, main_width)

        rdc = _draw_columns(rng, options["rez_de_chaussee_columns"], width, margin, gutter, rdc_ok,
                            "rez_de_chaussee_columns (différent de main)", exclude=main)
    span = None
    if rng.random() < options["headline_probability"]:
        span = rng.choices(options["headline_span"]["choice"], options["headline_span"]["weights"])[0]
        span = min(span, main - 1) if main >= 3 else None
    zones = [{"id": "main", "columns": _columns(main, width, margin, gutter)[1], "headline_span": span}]
    if rdc is not None:
        zones.append({"id": "rez_de_chaussee", "columns": _columns(rdc, width, margin, gutter)[1],
                      "headline_span": None})
    return {
        "version": LAYOUT_VERSION, "width": width, "height": height, "margin": margin, "gutter": gutter,
        "zones": zones, "rez_de_chaussee_share": share, "zone_gap_px": options["zone_gap_px"],
    }


def place_zones(draws: dict, *, top: float, bottom: float, min_zone_height: float) -> dict:
    """Deterministic vertical placement; returns a plan accepted by check_plan."""
    if not all(_number(v) for v in (top, bottom, min_zone_height)) or not \
            draws["margin"] <= top < bottom <= draws["height"] - draws["margin"]:
        raise LayoutError("Bornes verticales invalides (marges de page)")
    plan = deepcopy(draws)
    gap = plan.pop("zone_gap_px")
    x0, x1 = plan["margin"], plan["width"] - plan["margin"]
    plan["zone_rules"] = []
    share = plan["rez_de_chaussee_share"]
    if share is None:
        plan["zones"][0]["bbox"] = [x0, top, x1, bottom]
    else:
        split = round(bottom - share * (bottom - top), 6)
        plan["zones"][0]["bbox"] = [x0, top, x1, split - gap / 2]
        plan["zones"][1]["bbox"] = [x0, split + gap / 2, x1, bottom]
        plan["zone_rules"].append([x0, split - RULE_PX / 2, x1, split + RULE_PX / 2])
    plan["min_zone_height"] = min_zone_height
    for zone in plan["zones"]:
        zone["headline_reserved"] = None
        zone["headline_body_band"] = None
    errors = check_plan(plan)
    if errors:
        raise LayoutError("Plan de mise en page invalide : " + "; ".join(errors[:5]))
    return plan


def small_body_size(normal: int, ratio: float) -> int:
    if isinstance(normal, bool) or not isinstance(normal, int) or normal < MIN_BODY_PX \
            or not _number(ratio) or not 0.6 <= ratio <= 1:
        raise LayoutError("Corps normal (entier ≥ 10) ou rapport invalide")
    return max(MIN_BODY_PX, round(normal * ratio))


def _zone(plan: dict, zone_id: str) -> dict:
    zone = next((z for z in plan["zones"] if z["id"] == zone_id), None)
    if zone is None:
        raise LayoutError(f"Zone inconnue : {zone_id!r}")
    return zone


def headline_rect(plan: dict, zone_id: str) -> list[float]:
    zone = _zone(plan, zone_id)
    span = zone["headline_span"]
    if span is None:
        raise LayoutError(f"Pas de titre large dans la zone {zone_id}")
    return [zone["columns"][0][0], zone["bbox"][1], zone["columns"][span - 1][1], zone["bbox"][3]]


def reserve_headline(plan: dict, zone_id: str, headline_bottom: float, gap: float) -> dict:
    """Return a copy of the plan with the reserved headline rectangle recorded.

    The reservation spans the headline columns from the zone top down to
    headline_bottom + gap. The headline block itself keeps its ink envelope;
    the body of its article must stay inside the reserved columns, below it.
    """
    zone = _zone(plan, zone_id)
    x0, top, x1, bottom = headline_rect(plan, zone_id)
    if not _number(headline_bottom) or not _number(gap) or gap < 0 or headline_bottom < top:
        raise LayoutError("Bas du titre large ou espacement invalides")
    if headline_bottom + gap >= bottom:
        raise LayoutError("Le titre large remplit la zone")
    if zone["headline_reserved"] is not None:
        raise LayoutError("Titre large déjà réservé dans cette zone")
    result = deepcopy(plan)
    _zone(result, zone_id)["headline_reserved"] = [x0, top, x1, round(headline_bottom + gap, 6)]
    errors = check_plan(result)
    if errors:
        raise LayoutError("Réservation de titre invalide : " + "; ".join(errors[:5]))
    return result


def headline_columns(plan: dict, zone_id: str) -> list[list[float]]:
    """Rectangles of the covered columns below the reserved headline.

    The headline article body is balanced over exactly these columns, one block
    per column, before the body band is reserved.
    """
    zone = _zone(plan, zone_id)
    span, reserved = zone["headline_span"], zone["headline_reserved"]
    if span is None or reserved is None:
        raise LayoutError("Le titre large doit être réservé avant de couler son article")
    if zone["headline_body_band"] is not None:
        raise LayoutError("La bande du titre large est déjà réservée")
    return [[x0, reserved[3], x1, zone["bbox"][3]] for x0, x1 in zone["columns"][:span]]


def reserve_headline_band(plan: dict, zone_id: str, body_flow_bottom: float, gap: float,
                          min_space_below: float) -> dict:
    """Return a copy of the plan with the balanced body band of the headline article.

    The band spans the covered columns from the bottom of the headline
    reservation to body_flow_bottom + gap. body_flow_bottom comes from the
    renderer's preparation envelope (shared by both raster factors), not from
    the final ink. At least min_space_below must remain under the band.
    """
    zone = _zone(plan, zone_id)
    columns = headline_columns(plan, zone_id)
    top, zone_bottom = columns[0][1], zone["bbox"][3]
    if not all(_number(v) for v in (body_flow_bottom, gap, min_space_below)) or gap < 0 \
            or min_space_below <= 0 or body_flow_bottom <= top:
        raise LayoutError("Bas de bande, espacement ou espace restant invalides")
    bottom = round(body_flow_bottom + gap, 6)
    if bottom + min_space_below > zone_bottom:
        raise LayoutError("La bande du titre large ne laisse pas l'espace minimal sous elle")
    result = deepcopy(plan)
    _zone(result, zone_id)["headline_body_band"] = [columns[0][0], top, columns[-1][2], bottom]
    errors = check_plan(result)
    if errors:
        raise LayoutError("Bande de titre invalide : " + "; ".join(errors[:5]))
    return result


def columns_below(plan: dict, zone_id: str) -> list[list[float]]:
    """Column rectangles for ordinary articles: below the headline band if any."""
    zone = _zone(plan, zone_id)
    top, bottom = zone["bbox"][1], zone["bbox"][3]
    span = zone["headline_span"] or 0
    band = zone["headline_body_band"]
    if span and band is None:
        raise LayoutError("La bande du titre large doit être réservée avant les articles ordinaires")
    return [[x0, band[3] if index < span else top, x1, bottom]
            for index, (x0, x1) in enumerate(zone["columns"])]


def check_plan(plan: dict) -> list[str]:
    """Strict structure and geometric invariants of a placed plan; [] means valid."""
    if not isinstance(plan, dict):
        return ["plan : objet attendu"]
    if set(plan) != PLAN_KEYS:
        return ["plan : clés attendues " + ", ".join(sorted(PLAN_KEYS))]
    if plan["version"] != LAYOUT_VERSION:
        return ["version de plan inconnue"]
    width, height, margin, gutter = plan["width"], plan["height"], plan["margin"], plan["gutter"]
    for name, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int) or not PAGE_LIMITS[0] <= value <= PAGE_LIMITS[1]:
            return [f"{name} : entier dans {PAGE_LIMITS[0]}..{PAGE_LIMITS[1]} attendu"]
    if isinstance(margin, bool) or not isinstance(margin, int) or not 0 <= margin < min(width, height) / 2:
        return ["margin : entier positif inférieur à la demi-page attendu"]
    if not _number(gutter) or gutter < 0 or not _number(plan["min_zone_height"]) or plan["min_zone_height"] <= 0:
        return ["gutter ≥ 0 et min_zone_height > 0 finis attendus"]
    zones, rules, share = plan["zones"], plan["zone_rules"], plan["rez_de_chaussee_share"]
    if not isinstance(zones, list) or not all(isinstance(z, dict) and set(z) == ZONE_KEYS for z in zones):
        return ["zones : objets aux clés " + ", ".join(sorted(ZONE_KEYS)) + " attendus"]
    if [z["id"] for z in zones] not in (["main"], ["main", "rez_de_chaussee"]):
        return ["zones attendues : main, puis éventuellement rez_de_chaussee"]
    if not isinstance(rules, list) or not all(isinstance(r, list) and len(r) == 4 for r in rules):
        return ["zone_rules : liste de rectangles [x0, y0, x1, y1] attendue"]
    for zone in zones:
        if not (isinstance(zone["bbox"], list) and len(zone["bbox"]) == 4
                and isinstance(zone["columns"], list)
                and all(isinstance(c, list) and len(c) == 2 for c in zone["columns"])):
            return [f"{zone['id']} : bbox [x0, y0, x1, y1] et colonnes [x0, x1] attendues"]
    values = [v for z in zones for v in z["bbox"] + [c for col in z["columns"] for c in col]]
    values += [v for rule in rules for v in rule]
    values += [v for z in zones if isinstance(z["headline_reserved"], list) for v in z["headline_reserved"]]
    values += [v for z in zones if isinstance(z["headline_body_band"], list) for v in z["headline_body_band"]]
    if not all(_number(v) for v in values):
        return ["nombres non finis dans le plan"]
    errors = []
    two = len(zones) == 2
    if two != (share is not None):
        errors.append("rez_de_chaussee_share : nombre si et seulement si la zone existe")
    elif two and (not _number(share) or not 0 < share < 1):
        errors.append("rez_de_chaussee_share : nombre dans ]0, 1[ attendu")
    if len(rules) != len(zones) - 1:
        errors.append("un filet de zone par frontière est requis")
    if two and len(zones[0]["columns"]) == len(zones[1]["columns"]):
        errors.append("rez_de_chaussee : même nombre de colonnes que main")
    for index, zone in enumerate(zones):
        x0, y0, x1, y1 = zone["bbox"]
        label = zone["id"]
        if not (margin <= x0 < x1 <= width - margin) or not (margin <= y0 < y1 <= height - margin) \
                or y1 - y0 < plan["min_zone_height"]:
            errors.append(f"{label} : bbox hors page ou trop basse")
        columns = zone["columns"]
        if len(columns) < 2:
            errors.append(f"{label} : au moins deux colonnes")
        for a, b in zip(columns, columns[1:]):
            if b[0] - a[1] < gutter - 1e-6:
                errors.append(f"{label} : colonnes chevauchantes ou gouttière insuffisante")
        for c0, c1 in columns:
            if not (x0 - 1e-6 <= c0 < c1 <= x1 + 1e-6):
                errors.append(f"{label} : colonne hors de la zone")
        span = zone["headline_span"]
        span_ok = span is None or (
            label == "main" and not isinstance(span, bool) and isinstance(span, int)
            and 2 <= span <= len(columns) - 1
        )
        if not span_ok:
            errors.append(f"{label} : titre large invalide")
        reserved = zone["headline_reserved"]
        if reserved is not None:
            if not span_ok:
                pass  # the span error is already reported; never index with an invalid span
            elif span is None:
                errors.append(f"{label} : réservation de titre sans titre large")
            elif not isinstance(reserved, list) or len(reserved) != 4:
                errors.append(f"{label} : réservation de titre mal formée")
            else:
                rx0, ry0, rx1, ry1 = reserved
                if (rx0, ry0) != (columns[0][0], y0) or rx1 != columns[span - 1][1] or not y0 < ry1 < y1:
                    errors.append(f"{label} : réservation de titre hors de ses colonnes ou de la zone")
        band = zone["headline_body_band"]
        if band is not None:
            if not span_ok or span is None or not isinstance(reserved, list) or len(reserved) != 4:
                errors.append(f"{label} : bande de titre sans titre large réservé")
            elif not isinstance(band, list) or len(band) != 4:
                errors.append(f"{label} : bande de titre mal formée")
            elif (band[0], band[1], band[2]) != (reserved[0], reserved[3], reserved[2]) or not band[1] < band[3] < y1:
                errors.append(f"{label} : bande de titre hors de ses colonnes, de la réservation ou de la zone")
        if index:
            previous = zones[index - 1]["bbox"]
            rule = rules[index - 1] if index - 1 < len(rules) else None
            if y0 <= previous[3]:
                errors.append(f"{label} : zones qui se chevauchent")
            elif rule is None or not (
                previous[3] <= rule[1] < rule[3] <= y0 and rule[3] - rule[1] >= RULE_PX
                and rule[0] == x0 and rule[2] == x1
            ):
                errors.append(f"{label} : filet de zone absent, trop fin ou mal placé")
            elif two and _number(share):
                top, bottom = zones[0]["bbox"][1], y1
                split = (rule[1] + rule[3]) / 2
                if abs(split - (bottom - share * (bottom - top))) > 1e-3:
                    errors.append("rez_de_chaussee_share : incohérent avec la position du filet")
    return errors
