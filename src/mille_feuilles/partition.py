"""Leak-free train/dev/test partitions by source group.

Groups that share a normalized selectable unit (paragraph or title line, any
role) form one component and always land in the same partition. The plan is
recomputed from the verified catalog files, never trusted from a report.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from pathlib import Path

from .catalog import (
    TEXT_ROLES,
    load_catalog,
    normalize_unit,
    text_group,
    text_units,
    validate_catalog,
)
from .io import sha256, write_json
from .validation import load_json, safe_path

PARTITION_PATH = "assets/partition.json"
FORMAT = "mille-feuilles-partition"
METHOD = "components-sha256-greedy-v1"
_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}")


class PartitionError(ValueError):
    """A partition plan that cannot be produced or trusted."""


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def components(bundle_root: Path) -> list[dict]:
    """Connected components of source groups, from the verified catalog files."""
    bundle_root = Path(bundle_root)
    errors = validate_catalog(bundle_root)
    if errors:
        raise PartitionError("Catalogue non vérifié : " + "; ".join(errors[:5]))
    catalog = load_catalog(bundle_root)
    parent: dict[str, str] = {}

    def find(group: str) -> str:
        while parent[group] != group:
            parent[group] = parent[parent[group]]
            group = parent[group]
        return group

    owners: dict[str, str] = {}
    texts = [a for a in catalog["assets"] if a["kind"] == "text"]
    for asset in sorted(texts, key=lambda a: a["id"]):
        group = text_group(asset)
        parent.setdefault(group, group)
        value = safe_path(bundle_root, asset["path"]).read_text(encoding="utf-8")
        for unit, _, _ in text_units(value, asset["metadata"]["role"]):
            key = normalize_unit(unit)
            if key in owners:
                a, b = find(owners[key]), find(group)
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                owners[key] = group
    members: dict[str, dict] = {}
    for asset in texts:
        root = find(text_group(asset))
        item = members.setdefault(root, {"groups": set(), "asset_ids": [], "roles": set(), "chars": 0})
        item["groups"].add(text_group(asset))
        item["asset_ids"].append(asset["id"])
        item["roles"].add(asset["metadata"]["role"])
        item["chars"] += len(safe_path(bundle_root, asset["path"]).read_text(encoding="utf-8"))
    result = []
    for item in members.values():
        groups = sorted(item["groups"])
        result.append({
            "key": _digest("\x1f".join(groups)),
            "groups": groups,
            "asset_ids": sorted(item["asset_ids"]),
            "roles": [role for role in TEXT_ROLES if role in item["roles"]],
            "chars": item["chars"],
        })
    return sorted(result, key=lambda c: c["key"])


SEARCH_BUDGET = 200_000
# Bounds the recursion depth of the role cover (at most 3 steps per partition).
MAX_PARTITIONS = 32


def _role_cover(order: list[dict], positive: list[str]):
    """Disjoint components giving every partition all roles.

    Returns {partition: [component keys]}, None when no cover exists (search
    exhausted), or "budget" when the step budget ran out first.
    """
    used: set[str] = set()
    chosen = {name: [] for name in positive}
    covered = {name: set() for name in positive}
    steps = 0

    def search() -> bool | None:
        nonlocal steps
        target = next((n for n in positive if len(covered[n]) < len(TEXT_ROLES)), None)
        if target is None:
            return True
        role = next(r for r in TEXT_ROLES if r not in covered[target])
        for component in order:
            if component["key"] in used or role not in component["roles"]:
                continue
            steps += 1
            if steps > SEARCH_BUDGET:
                return None
            before = set(covered[target])
            used.add(component["key"])
            chosen[target].append(component["key"])
            covered[target].update(component["roles"])
            result = search()
            if result is not False:
                return result
            used.discard(component["key"])
            chosen[target].pop()
            covered[target] = before
        return False

    result = search()
    if result is None:
        return "budget"
    return chosen if result else None


def _check_parameters(ratios: Mapping[str, float], seed: int) -> dict[str, float]:
    if not isinstance(ratios, Mapping) or not ratios:
        raise PartitionError("ratios : dictionnaire non vide attendu")
    clean = {}
    for name, value in ratios.items():
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise PartitionError(f"nom de partition invalide : {name!r}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PartitionError(f"ratio invalide pour {name} : {value!r}")
        try:
            as_float = float(value)  # huge integers overflow here, not later
        except OverflowError:
            raise PartitionError(f"ratio hors des flottants finis pour {name}") from None
        if not math.isfinite(as_float) or as_float < 0:
            raise PartitionError(f"ratio invalide pour {name} : {value!r}")
        clean[name] = value
    if len(clean) > MAX_PARTITIONS:
        raise PartitionError(f"au plus {MAX_PARTITIONS} partitions")
    if not max(clean.values()) > 0:
        raise PartitionError("au moins un ratio doit être positif")
    try:
        total = math.fsum(float(v) for v in clean.values())
    except OverflowError:
        total = math.inf
    if not math.isfinite(total):
        raise PartitionError("la somme des ratios doit être finie")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**53:
        raise PartitionError("graine hors intervalle 0..2^53-1")
    return clean


def _plan(bundle_root: Path, ratios: Mapping[str, float], seed: int) -> dict:
    ratios = _check_parameters(ratios, seed)
    comps = components(bundle_root)
    order = sorted(comps, key=lambda c: (_digest(f"{seed}:{c['key']}"), c["key"]))
    # Larger partitions are served first, then by name: stable and order-free.
    positive = sorted((n for n, v in ratios.items() if v > 0), key=lambda n: (-ratios[n], n))
    total = sum(c["chars"] for c in comps)
    # Scale by the largest ratio first, for a stable division (the sum is finite).
    scale = max(ratios.values())
    shares = {name: ratios[name] / scale for name in positive}
    weight = sum(shares.values())
    target = {name: total * shares[name] / weight for name in positive}
    assigned: dict[str, str] = {}
    chars = {name: 0 for name in positive}
    roles = {name: set() for name in positive}

    def give(component: dict, name: str) -> None:
        assigned[component["key"]] = name
        chars[name] += component["chars"]
        roles[name].update(component["roles"])

    # Phase 1: every positive partition must cover all roles. Depth-first
    # search over free components, in seeded order: complete (each step must
    # cover the first missing role of the first incomplete partition), bounded.
    cover = _role_cover(order, positive)
    if cover is None:
        available = {role: sum(role in c["roles"] for c in comps) for role in TEXT_ROLES}
        raise PartitionError(
            "Partition impossible sans fuite (recherche exhaustive) : "
            f"{len(positive)} partitions à ratio positif, {len(comps)} composantes, "
            f"composantes par rôle {available}"
        )
    if cover == "budget":
        raise PartitionError(
            f"Aucune couverture des rôles trouvée dans la limite de {SEARCH_BUDGET} étapes : "
            "impossibilité non démontrée ; réduire le nombre de partitions ou fusionner des rôles"
        )
    for name, keys in cover.items():
        for key in keys:
            give(next(c for c in comps if c["key"] == key), name)
    # Phase 2: largest character deficit first, ties by partition name.
    for component in order:
        if component["key"] not in assigned:
            name = max(positive, key=lambda n: (target[n] - chars[n], -positive.index(n)))
            give(component, name)
    partitions = {name: [] for name in sorted(ratios)}
    for component in comps:
        partitions[assigned[component["key"]]].extend(component["asset_ids"])
    return {
        "format": FORMAT,
        "version": "1",
        "method": METHOD,
        "seed": seed,
        "ratios": dict(sorted(ratios.items())),
        "catalog_sha256": sha256(Path(bundle_root) / "assets/catalog.json"),
        "partitions": {name: sorted(ids) for name, ids in partitions.items()},
        "components": [
            {"key": c["key"], "partition": assigned[c["key"]], "groups": c["groups"], "chars": c["chars"]}
            for c in comps
        ],
        "characters": {name: chars.get(name, 0) for name in sorted(ratios)},
    }


def assign_partitions(bundle_root: Path, ratios: Mapping[str, float], seed: int) -> dict:
    """Write assets/partition.json once; an identical existing plan is returned."""
    bundle_root = Path(bundle_root)
    plan = _plan(bundle_root, ratios, seed)
    path = safe_path(bundle_root, PARTITION_PATH)
    if path.exists():
        try:
            existing = load_json(path)
        except (OSError, ValueError) as exc:
            raise PartitionError(f"Partition existante illisible, non écrasée : {exc}") from exc
        if existing != plan:
            raise PartitionError("Une partition différente existe déjà ; elle n'est pas écrasée")
        return existing
    write_json(path, plan)
    return plan


def load_partition(bundle_root: Path, name: str) -> set[str]:
    """Text asset IDs of one partition, after recomputing the stored plan."""
    bundle_root = Path(bundle_root)
    try:
        stored = load_json(safe_path(bundle_root, PARTITION_PATH))
    except (OSError, ValueError) as exc:
        raise PartitionError(f"Partition illisible : {exc}") from exc
    if not isinstance(stored, dict) or (stored.get("format"), stored.get("version"), stored.get("method")) != (
        FORMAT, "1", METHOD
    ):
        raise PartitionError("Format de partition non pris en charge")
    if _plan(bundle_root, stored.get("ratios"), stored.get("seed")) != stored:
        raise PartitionError("La partition enregistrée ne correspond pas au catalogue vérifié")
    if name not in stored["partitions"]:
        raise PartitionError(f"Partition inconnue : {name!r}")
    return set(stored["partitions"][name])
