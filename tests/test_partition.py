"""Partitions by connected source groups: no shared unit crosses partitions."""

import json
import shutil

import pytest
from test_catalog import make_source, prose, standard_docs, titles

from mille_feuilles.catalog import import_texts, load_catalog, normalize_unit, text_units
from mille_feuilles.io import ROOT
from mille_feuilles.partition import (
    PartitionError,
    assign_partitions,
    components,
    load_partition,
)

RATIOS = {"train": 0.6, "dev": 0.2, "test": 0.2}


def build(tmp_path, docs, name="bundle"):
    root = tmp_path / name
    report = import_texts(make_source(tmp_path / f"{name}-src", docs), root)
    assert report["status"] == "pass", report
    return root


def roles_by_asset(root):
    return {a["id"]: a["metadata"]["role"] for a in load_catalog(root)["assets"] if a["kind"] == "text"}


def units_by_asset(root):
    result = {}
    for asset in load_catalog(root)["assets"]:
        if asset["kind"] == "text":
            text = (root / asset["path"]).read_text(encoding="utf-8")
            result[asset["id"]] = {normalize_unit(u) for u, _, _ in text_units(text, asset["metadata"]["role"])}
    return result


def test_shared_paragraph_or_title_line_unites_groups_across_roles(tmp_path):
    shared = prose("partagé", 1)
    docs = standard_docs(groups=("g1", "g2", "g3", "g4"))
    # g1 body and g2 advertisement share one paragraph (whitespace differs).
    docs[0] = (docs[0][0], "g1", "body", docs[0][3] + "\n" + shared)
    docs[7] = (docs[7][0], "g2", "advertisement", docs[7][3] + "\n" + shared.replace(" ", "  \n", 1))
    # g3 and g4 share one title line.
    docs[10] = (docs[10][0], "g3", "title", titles("g3") + "Rubrique commune\n")
    docs[14] = (docs[14][0], "g4", "title", "Rubrique commune\n" + titles("g4"))
    groups = sorted(c["groups"] for c in components(build(tmp_path, docs)))
    assert groups == [["g1", "g2"], ["g3", "g4"]]


def test_plan_keeps_components_whole_and_gives_every_role_to_every_partition(tmp_path):
    root = build(tmp_path, standard_docs(groups=[f"g{i}" for i in range(9)]))
    plan = assign_partitions(root, RATIOS, seed=7)
    roles = roles_by_asset(root)
    owner = {}
    for name, ids in plan["partitions"].items():
        assert {roles[i] for i in ids} == {"body", "title", "advertisement"}
        for asset_id in ids:
            assert asset_id not in owner
            owner[asset_id] = name
    assert set(owner) == set(roles)
    # No normalized unit is present in two partitions.
    units = units_by_asset(root)
    seen = {}
    for asset_id, values in units.items():
        for unit in values:
            assert seen.setdefault(unit, owner[asset_id]) == owner[asset_id]
    on_disk = json.loads((root / "assets/partition.json").read_text(encoding="utf-8"))
    assert on_disk == plan
    assert load_partition(root, "dev") == set(plan["partitions"]["dev"])


def test_shared_units_force_the_same_partition(tmp_path):
    docs = standard_docs(groups=[f"g{i}" for i in range(9)])
    shared = prose("commun", 1)
    for index in (0, 4, 8):  # bodies of g0, g1, g2
        docs[index] = (docs[index][0], docs[index][1], "body", docs[index][3] + "\n" + shared)
    root = build(tmp_path, docs)
    plan = assign_partitions(root, RATIOS, seed=3)
    owners = {c["partition"] for c in plan["components"] if set(c["groups"]) & {"g0", "g1", "g2"}}
    assert len(owners) == 1
    assert [len(c["groups"]) for c in plan["components"]].count(3) == 1


def test_plan_is_independent_of_manifest_order_and_deterministic(tmp_path):
    docs = standard_docs(groups=[f"g{i}" for i in range(8)])
    one = assign_partitions(build(tmp_path, docs, "one"), RATIOS, seed=11)
    two = assign_partitions(build(tmp_path, list(reversed(docs)), "two"), RATIOS, seed=11)
    assert one == two
    other = assign_partitions(build(tmp_path, docs, "three"), RATIOS, seed=12)
    assert other["seed"] == 12 and other["catalog_sha256"] == one["catalog_sha256"]


def test_existing_plan_is_returned_if_identical_and_never_overwritten(tmp_path):
    root = build(tmp_path, standard_docs(groups=[f"g{i}" for i in range(6)]))
    first = assign_partitions(root, RATIOS, seed=1)
    before = (root / "assets/partition.json").read_bytes()
    assert assign_partitions(root, RATIOS, seed=1) == first
    with pytest.raises(PartitionError):
        assign_partitions(root, RATIOS, seed=2)
    with pytest.raises(PartitionError):
        assign_partitions(root, {"train": 0.8, "dev": 0.1, "test": 0.1}, seed=1)
    assert (root / "assets/partition.json").read_bytes() == before


def test_impossible_partition_is_a_demonstrated_error_and_writes_nothing(tmp_path):
    root = build(tmp_path, standard_docs(groups=("g1", "g2")))
    with pytest.raises(PartitionError, match="recherche exhaustive") as caught:
        assign_partitions(root, RATIOS, seed=5)
    assert "3 partitions à ratio positif, 2 composantes" in str(caught.value)
    assert not (root / "assets/partition.json").exists()


ROLE_DOCS = {
    "body": lambda seed: prose(seed),
    "title": lambda seed: titles(seed),
    "advertisement": lambda seed: prose(seed + "-annonce", 1, 10),
}


def groups_with_roles(spec):
    """spec: {group: roles}; one original document per (group, role)."""
    return [
        (f"{group}-{role}", group, role, ROLE_DOCS[role](f"{group}{role}"))
        for group, roles in spec.items()
        for role in roles
    ]


COVER_CASE = {
    "a": ("body", "title"),
    "b": ("body", "advertisement"),
    "c": ("title", "advertisement"),
    "d": ("body",),
}


@pytest.mark.parametrize("seed", [14] + list(range(0, 40, 3)))
def test_role_cover_is_found_where_first_fit_could_fail(tmp_path, seed):
    # Only {a, b} | {c, d} gives both partitions all roles; a first-fit choice
    # in some seeded orders takes d then a, b for one side and starves the other.
    root = build(tmp_path, groups_with_roles(COVER_CASE))
    plan = assign_partitions(root, {"train": 0.5, "dev": 0.5}, seed=seed)
    sides = sorted(sorted(set(c["groups"][0] for c in plan["components"] if c["partition"] == name))
                   for name in ("train", "dev"))
    assert sides == [["a", "b"], ["c", "d"]]


def test_search_budget_exhaustion_is_not_reported_as_impossibility(tmp_path, monkeypatch):
    from mille_feuilles import partition

    root = build(tmp_path, groups_with_roles(COVER_CASE))
    monkeypatch.setattr(partition, "SEARCH_BUDGET", 1)
    with pytest.raises(PartitionError, match="non démontrée"):
        assign_partitions(root, {"train": 0.5, "dev": 0.5}, seed=14)
    assert not (root / "assets/partition.json").exists()


def test_single_train_partition_and_zero_ratio_partition(tmp_path):
    root = build(tmp_path, standard_docs(groups=("g1", "g2")))
    plan = assign_partitions(root, {"train": 1, "test": 0}, seed=0)
    assert set(plan["partitions"]["train"]) == set(roles_by_asset(root))
    assert plan["partitions"]["test"] == []
    assert load_partition(root, "test") == set()


@pytest.mark.parametrize(
    "ratios, seed",
    [({}, 0), ({"Train": 1}, 0), ({"train": -1}, 0), ({"train": float("nan")}, 0),
     ({"train": 0}, 0), ({"train": True}, 0), ({"train": 10**400}, 0), ({"train": 1, "dev": 10**400}, 0), ({"train": 10**308, "dev": 10**308}, 0), ({"train": 1}, -1), ({"train": 1}, 2**53), ({"train": 1}, 1.5)],
)
def test_invalid_parameters_are_refused(tmp_path, ratios, seed):
    root = build(tmp_path, standard_docs(groups=("g1",)))
    with pytest.raises(PartitionError):
        assign_partitions(root, ratios, seed)
    assert not (root / "assets/partition.json").exists()


def test_tampered_plan_or_changed_catalog_is_refused(tmp_path):
    root = build(tmp_path, standard_docs(groups=[f"g{i}" for i in range(6)]))
    plan = assign_partitions(root, RATIOS, seed=4)
    path = root / "assets/partition.json"
    original = path.read_text(encoding="utf-8")
    moved = json.loads(original)
    asset = moved["partitions"]["test"].pop()
    moved["partitions"]["train"] = sorted(moved["partitions"]["train"] + [asset])
    path.write_text(json.dumps(moved), encoding="utf-8")
    with pytest.raises(PartitionError):
        load_partition(root, "train")
    path.write_text(original, encoding="utf-8")
    assert load_partition(root, "train") == set(plan["partitions"]["train"])
    with pytest.raises(PartitionError):
        load_partition(root, "validation")
    # A catalog edit (here: one text removed) invalidates the stored plan.
    catalog = load_catalog(root)
    catalog["assets"] = [a for a in catalog["assets"] if a["id"] != asset]
    (root / "assets/catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PartitionError):
        load_partition(root, "train")


def test_unverified_catalog_cannot_be_partitioned(tmp_path):
    root = build(tmp_path, standard_docs(groups=("g1", "g2", "g3")))
    asset = next(a for a in load_catalog(root)["assets"] if a["kind"] == "text")
    (root / asset["path"]).write_text("modifié\n", encoding="utf-8")
    with pytest.raises(PartitionError, match="non vérifié"):
        components(root)


def test_embedded_020_catalog_is_one_component_train_only(tmp_path):
    shutil.copytree(ROOT / "assets", tmp_path / "assets")
    comps = components(tmp_path)
    assert len(comps) == 1
    with pytest.raises(PartitionError):
        assign_partitions(tmp_path, {"train": 0.9, "dev": 0.1}, seed=0)
    plan = assign_partitions(tmp_path, {"train": 1}, seed=0)
    assert len(plan["partitions"]["train"]) == 3
    assert not (ROOT / "assets/partition.json").exists()


def test_large_ratios_keep_proportions_and_overflowing_sum_is_refused(tmp_path):
    spec = {f"g{i:02d}": ("body", "title", "advertisement") for i in range(12)}
    small = assign_partitions(build(tmp_path, groups_with_roles(spec), "two"), {"train": 2, "dev": 1}, seed=0)
    large = assign_partitions(build(tmp_path, groups_with_roles(spec), "big"), {"train": 2e307, "dev": 1e307}, seed=0)
    assert small["partitions"] == large["partitions"]
    assert small["characters"] == large["characters"]
    root = build(tmp_path, groups_with_roles(spec), "huge")
    with pytest.raises(PartitionError, match="somme des ratios"):
        assign_partitions(root, {"train": 1e308, "dev": 1e308}, seed=0)
    assert not (root / "assets/partition.json").exists()


def test_number_of_partitions_is_bounded_before_search(tmp_path):
    from mille_feuilles.partition import MAX_PARTITIONS

    root = build(tmp_path, standard_docs(groups=("g1",)))
    ratios = {f"p{i}": 1 for i in range(MAX_PARTITIONS + 1)}
    with pytest.raises(PartitionError, match=f"au plus {MAX_PARTITIONS}"):
        assign_partitions(root, ratios, seed=0)
    # At the bound, an impossible plan is still a controlled error, not a RecursionError.
    with pytest.raises(PartitionError, match="recherche exhaustive"):
        assign_partitions(root, {f"p{i}": 1 for i in range(MAX_PARTITIONS)}, seed=0)
