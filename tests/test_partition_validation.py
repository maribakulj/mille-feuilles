"""A filtered dataset proves partition consistency without opening held-out text."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from mille_feuilles.validation import validate_dataset, validate_partition_receipt
from test_provenance_v3 import dataset as base_dataset, page as page  # noqa: F401
from test_provenance_v3 import digest, write_json


def read(root, relative):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def edit(root, relative, mutate):
    value = read(root, relative)
    mutate(value)
    write_json(root / relative, value)


def component(groups, partition, chars):
    groups = sorted(groups)
    return {"key": hashlib.sha256("\x1f".join(groups).encode()).hexdigest(),
            "groups": groups, "partition": partition, "chars": chars}


def reseal(root, *, source_changed=False):
    """Rehash all metadata after a mutation to exercise semantics beyond hashes."""
    manifest = read(root, "manifest.json")
    receipt = manifest["extensions"]["mf:partition"]
    if source_changed:
        edit(root, "provenance/partition.json", lambda plan: plan.update(
            catalog_sha256=digest(root / "provenance/source-catalog.json")))
    receipt["sha256"] = digest(root / "provenance/partition.json")
    receipt["source_catalog_sha256"] = digest(root / "provenance/source-catalog.json")
    edit(root, "config.json", lambda config: config.update(partition=deepcopy(receipt)))
    for ref in (manifest["config"], manifest["assets"], *manifest["pages"]):
        ref["sha256"] = digest(root / ref["path"])
    manifest["artifacts"] = [
        {"path": path.relative_to(root).as_posix(), "sha256": digest(path), "role": "fixture"}
        for path in sorted(root.rglob("*")) if path.is_file() and path.name != "manifest.json"
    ]
    write_json(root / "manifest.json", manifest)


@pytest.fixture
def partitioned(request):
    root = request.getfixturevalue("base_dataset")
    registry = read(root, "assets.json")
    body = next(asset for asset in registry["assets"] if asset["id"] == "body")
    for asset in registry["assets"]:
        if asset["kind"] == "text":
            asset["metadata"]["role"] = asset["id"]
    ad = deepcopy(body)
    ad.update(id="advertisement", path="assets/advertisement.txt")
    ad["metadata"] = {"source_document_id": "document_ad", "source_group_id": "group_ad",
                      "role": "advertisement"}
    (root / ad["path"]).write_text("Annonce originale.", encoding="utf-8")
    ad["sha256"] = digest(root / ad["path"])
    registry["assets"].append(ad)
    source = deepcopy(registry)
    partitions = {"train": ["advertisement", "body", "title"], "dev": [], "test": []}
    for partition in ("dev", "test"):
        for role in ("body", "title", "advertisement"):
            asset = deepcopy(ad)
            asset.update(id=f"{partition}_{role}", path=f"assets/excluded/{partition}_{role}.txt",
                         sha256=hashlib.sha256(f"{partition}:{role}".encode()).hexdigest())
            asset["metadata"] = {"source_document_id": f"document_{partition}_{role}",
                                 "source_group_id": f"group_{partition}", "role": role}
            source["assets"].append(asset)
            partitions[partition].append(asset["id"])
        partitions[partition].sort()
    write_json(root / "assets.json", registry)
    write_json(root / "assets/catalog.json", registry)
    write_json(root / "provenance/source-catalog.json", source)
    train_chars = sum(len((root / asset["path"]).read_text(encoding="utf-8"))
                      for asset in registry["assets"] if asset["kind"] == "text")
    plan = {
        "format": "mille-feuilles-partition", "version": "1", "seed": 42,
        "method": "components-sha256-greedy-v1", "ratios": {"train": 6, "dev": 2, "test": 2},
        "catalog_sha256": digest(root / "provenance/source-catalog.json"),
        "partitions": partitions,
        "components": sorted([
            component(["group_ad", "group_body", "group_title"], "train", train_chars),
            component(["group_dev"], "dev", 60), component(["group_test"], "test", 65),
        ], key=lambda item: item["key"]),
        "characters": {"train": train_chars, "dev": 60, "test": 65},
    }
    write_json(root / "provenance/partition.json", plan)
    receipt = {"version": "1", "name": "train", "path": "provenance/partition.json",
               "sha256": digest(root / "provenance/partition.json"),
               "source_catalog_path": "provenance/source-catalog.json",
               "source_catalog_sha256": digest(root / "provenance/source-catalog.json")}
    edit(root, "manifest.json", lambda manifest: manifest.update(extensions={"mf:partition": receipt}))
    edit(root, "config.json", lambda config: config.update(render={"partition": "train"}))
    edit(root, "pages/p1.json", lambda page: page["provenance"]["parameters"].update(partition="train"))
    reseal(root)
    return root


def receipt_errors(root):
    return validate_partition_receipt(root, read(root, "manifest.json"), read(root, "assets.json"))


def test_receipt_and_dataset_pass_without_excluded_text_files(partitioned):
    assert not (partitioned / "assets/excluded").exists()
    assert receipt_errors(partitioned) == []
    assert validate_dataset(partitioned, verify_exports=False)["errors"] == []


def test_receipt_reader_opens_only_metadata_never_pages_or_source_text(partitioned, monkeypatch):
    read_bytes, read_text = Path.read_bytes, Path.read_text
    opened = []

    def checked_bytes(path):
        opened.append(path.relative_to(partitioned).as_posix())
        assert path.suffix == ".json" and "pages" not in path.parts
        return read_bytes(path)

    def checked_text(path, *args, **kwargs):
        opened.append(path.relative_to(partitioned).as_posix())
        assert path.suffix == ".json" and "pages" not in path.parts
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", checked_bytes)
    monkeypatch.setattr(Path, "read_text", checked_text)
    assert receipt_errors(partitioned) == []
    assert "provenance/source-catalog.json" in opened


@pytest.mark.parametrize("relative", ["provenance/partition.json", "provenance/source-catalog.json",
                                     "assets/catalog.json", "config.json"])
def test_partition_metadata_requires_artifact_coverage(partitioned, relative):
    edit(partitioned, "manifest.json", lambda manifest: manifest.update(
        artifacts=[item for item in manifest["artifacts"] if item["path"] != relative]))
    assert any("missing artifact" in error for error in receipt_errors(partitioned))


@pytest.mark.parametrize("relative", ["provenance/partition.json", "provenance/source-catalog.json",
                                     "assets/catalog.json", "config.json"])
def test_rehashed_duplicate_keys_are_rejected(partitioned, relative):
    path = partitioned / relative
    content = path.read_text(encoding="utf-8")
    path.write_text('{"injected":1,"injected":2,' + content[1:], encoding="utf-8")
    # For config, reseal would parse it: manually refresh its manifest hash instead.
    if relative == "config.json":
        edit(partitioned, "manifest.json", lambda manifest: manifest["config"].update(sha256=digest(path)))
    else:
        reseal(partitioned)
    assert any("duplicate JSON key" in error for error in receipt_errors(partitioned))


@pytest.mark.parametrize("mutate,fragment", [
    (lambda plan: plan["partitions"]["train"].append("dev_body"), "multiple partitions"),
    (lambda plan: plan["partitions"]["train"].remove("body"), "cover source text assets exactly"),
    (lambda plan: plan["ratios"].update(train=0), "zero-weight partition"),
    (lambda plan: plan.update(ratios={"train": 0, "dev": 0, "test": 0}), "positive sum"),
    (lambda plan: plan["ratios"].update(train=True), "not of type"),
    (lambda plan: plan["characters"].update(train=71), "component totals"),
    (lambda plan: plan["components"][0].update(partition="unknown"), "unknown partition"),
    (lambda plan: plan["components"].append(deepcopy(plan["components"][0])), "exactly once"),
    (lambda plan: plan["components"][0].update(key="a" * 64), "canonical"),
    (lambda plan: plan.update(catalog_sha256="a" * 64), "catalog_sha256 differs"),
    (lambda plan: plan.update(version="2"), "expected"),
])
def test_rehashed_plan_semantic_corruption_fails(partitioned, mutate, fragment):
    edit(partitioned, "provenance/partition.json", mutate)
    reseal(partitioned)
    errors = receipt_errors(partitioned)
    assert any(fragment in error for error in errors), errors
    assert not any("SHA-256 mismatch" in error for error in errors)


@pytest.mark.parametrize("field,value", [("path", "../partition.json"),
                                         ("source_catalog_path", "/tmp/source.json"),
                                         ("name", "train\n"), ("sha256", "a" * 64)])
def test_invalid_receipt_paths_name_or_hash_fail(partitioned, field, value):
    edit(partitioned, "manifest.json", lambda manifest: manifest["extensions"]["mf:partition"].update(
        {field: value}))
    assert receipt_errors(partitioned)


def test_external_symlink_for_catalog_is_rejected_before_reading(partitioned, tmp_path):
    path = partitioned / "provenance/source-catalog.json"
    outside = tmp_path.parent / f"outside-{tmp_path.name}.json"
    outside.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    assert any("escapes dataset root" in error for error in receipt_errors(partitioned))


@pytest.mark.parametrize("relative", ["assets.json", "assets/catalog.json"])
def test_selected_catalog_and_registry_must_include_exact_selected_ids(partitioned, relative):
    extra = next(a for a in read(partitioned, "provenance/source-catalog.json")["assets"]
                 if a["id"] == "dev_body")
    edit(partitioned, relative, lambda registry: registry["assets"].append(extra))
    reseal(partitioned)
    assert any("text ids differ" in error for error in receipt_errors(partitioned))


@pytest.mark.parametrize("relative", ["assets.json", "assets/catalog.json"])
@pytest.mark.parametrize("field,value", [("sha256", "a" * 64), ("path", "assets/other.txt"),
                                         ("source_document_id", "forged"),
                                         ("source_group_id", "forged"), ("role", "title")])
def test_selected_identity_is_bound_to_original_catalog(partitioned, relative, field, value):
    def mutate(registry):
        asset = next(a for a in registry["assets"] if a["id"] == "body")
        (asset if field in ("sha256", "path") else asset["metadata"])[field] = value
    edit(partitioned, relative, mutate)
    reseal(partitioned)
    assert any("selected asset differs" in error for error in receipt_errors(partitioned))


@pytest.mark.parametrize("field", ["source_group_id", "source_document_id", "sha256"])
def test_source_identity_cannot_cross_partitions_even_after_rehash(partitioned, field):
    def mutate(catalog):
        body = next(a for a in catalog["assets"] if a["id"] == "body")
        dev = next(a for a in catalog["assets"] if a["id"] == "dev_body")
        if field == "sha256":
            dev[field] = body[field]
        else:
            dev["metadata"][field] = body["metadata"][field]
    edit(partitioned, "provenance/source-catalog.json", mutate)
    reseal(partitioned, source_changed=True)
    assert any("crosses partitions" in error for error in receipt_errors(partitioned))


def test_positive_partition_must_have_all_roles(partitioned):
    def mutate(plan):
        plan["partitions"]["dev"].remove("dev_title")
        plan["partitions"]["test"] = sorted(plan["partitions"]["test"] + ["dev_title"])
    edit(partitioned, "provenance/partition.json", mutate)
    reseal(partitioned)
    assert any("lacks required text roles" in error for error in receipt_errors(partitioned))


def test_zero_weight_empty_partition_is_supported(partitioned):
    def mutate(plan):
        plan["partitions"]["unused"] = []
        plan["ratios"]["unused"] = 0
        plan["characters"]["unused"] = 0
    edit(partitioned, "provenance/partition.json", mutate)
    reseal(partitioned)
    assert receipt_errors(partitioned) == []


def test_artifact_cannot_smuggle_an_excluded_text_outside_selected_registry(partitioned):
    asset = next(a for a in read(partitioned, "provenance/source-catalog.json")["assets"]
                 if a["id"] == "dev_body")
    path = partitioned / asset["path"]
    path.parent.mkdir(parents=True)
    path.write_text("dev:body", encoding="utf-8")
    reseal(partitioned)
    assert any("artifact contains excluded text" in error for error in receipt_errors(partitioned))


@pytest.mark.parametrize("field,value", [("role", []), ("source_group_id", {}),
                                         ("source_document_id", [])])
def test_malformed_source_metadata_returns_errors_without_crashing(partitioned, field, value):
    edit(partitioned, "provenance/source-catalog.json", lambda catalog:
         catalog["assets"][0]["metadata"].update({field: value}))
    reseal(partitioned, source_changed=True)
    assert receipt_errors(partitioned)


def test_legacy_catalog_can_use_document_identity_as_group(partitioned):
    for relative in ("provenance/source-catalog.json", "assets/catalog.json", "assets.json"):
        edit(partitioned, relative, lambda catalog: catalog["assets"][0]["metadata"].pop("source_group_id"))
    def update_component(plan):
        train = next(item for item in plan["components"] if item["partition"] == "train")
        train.update(component(["document_body", "group_title", "group_ad"], "train", train["chars"]))
    edit(partitioned, "provenance/partition.json", update_component)
    reseal(partitioned, source_changed=True)
    assert receipt_errors(partitioned) == []


@pytest.mark.parametrize("ratios", [{"train": 1e308, "dev": 1e308, "test": 1e308},
                                    {"train": -1, "dev": 1, "test": 1}])
def test_invalid_weight_total_is_controlled(partitioned, ratios):
    edit(partitioned, "provenance/partition.json", lambda plan: plan.update(ratios=ratios))
    reseal(partitioned)
    assert receipt_errors(partitioned)


def test_page_partition_is_checked_by_dataset_not_metadata_preflight(partitioned):
    edit(partitioned, "pages/p1.json", lambda page: page["provenance"]["parameters"].update(partition="dev"))
    reseal(partitioned)
    assert receipt_errors(partitioned) == []
    assert any("page partition differs" in error
               for error in validate_dataset(partitioned, verify_exports=False)["errors"])


def test_absent_receipt_cannot_hide_partitioned_config(partitioned):
    edit(partitioned, "manifest.json", lambda manifest: manifest.pop("extensions"))
    assert any("requires a manifest" in error for error in receipt_errors(partitioned))


def test_config_and_manifest_receipts_must_be_equal(partitioned):
    edit(partitioned, "config.json", lambda config: config["partition"].update(name="dev"))
    manifest = read(partitioned, "manifest.json")
    manifest["config"]["sha256"] = digest(partitioned / "config.json")
    for artifact in manifest["artifacts"]:
        if artifact["path"] == "config.json":
            artifact["sha256"] = manifest["config"]["sha256"]
    write_json(partitioned / "manifest.json", manifest)
    assert any("receipt/name differ" in error for error in receipt_errors(partitioned))
