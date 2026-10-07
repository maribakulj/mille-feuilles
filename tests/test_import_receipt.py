"""Import receipts bind accepted identities without opening excluded text."""

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from mille_feuilles.io import sha256, write_json
from mille_feuilles.validation import load_json, validate_dataset, validate_import_receipt
from test_provenance_v3 import dataset as legacy_dataset, page as page  # noqa: F401


REPORT = "provenance/import-report.json"
CATALOG = "assets/catalog.json"
SOURCE = "provenance/source-catalog.json"


def asset(identity, role):
    return {
        "id": identity, "kind": "text", "path": f"assets/excluded/{identity}.txt",
        "sha256": hashlib.sha256(identity.encode()).hexdigest(),
        "source_uri": f"urn:fixture:{identity}",
        "rights": {"status": "verified", "license": "CC0-1.0", "attribution": "fixture",
                   "evidence_uri": "assets/NOTICE.txt", "redistribution_allowed": True},
        "metadata": {"source_document_id": f"doc-{identity}", "source_group_id": identity,
                     "role": role, "language": "fr",
                     "evidence_files": [{"path": "assets/NOTICE.txt", "sha256": "a" * 64}]},
    }


def accepted(catalog):
    return [
        {"asset_id": item["id"], "sha256": item["sha256"],
         **{key: item["metadata"][key] for key in ("source_document_id", "source_group_id", "role")}}
        for item in catalog["assets"] if item["kind"] == "text"
    ]


@pytest.fixture(params=[False, True], ids=["unpartitioned", "partitioned"])
def metadata_lot(tmp_path, request):
    """Only JSON metadata exists; even selected text files are absent."""
    catalog = {"schema_version": "0.3.0", "assets": [
        asset("body", "body"), asset("title", "title"), asset("ad", "advertisement"),
    ]}
    source = deepcopy(catalog)
    source["assets"].append(asset("held_out", "body"))
    write_json(tmp_path / CATALOG, catalog)
    write_json(tmp_path / SOURCE, source)
    report = {
        "format": "mille-feuilles-import-report", "version": "1", "status": "pass",
        "accepted": accepted(source if request.param else catalog), "rejected": [],
        "exclusions": {"documents": {"status": "not_evaluated"},
                       "ngrams": {"status": "not_evaluated"}},
        "external_protection": "NOT EVALUATED",
    }
    write_json(tmp_path / REPORT, report)
    manifest = {
        "schema_version": "0.3.0", "dataset_id": "receipt_fixture",
        "profile": "fr_press_19c_columns_4_6",
        "generator": {"commit": "a" * 40, "dirty": False,
                      "environment_path": "environment.json", "environment_sha256": "a" * 64},
        "config": {"path": "config.json", "sha256": "a" * 64},
        "assets": {"path": "assets.json", "sha256": "a" * 64},
        "rng": {"algorithm": "fixture", "version": "1", "seed": 1},
        "calibration": {"protocol_path": "protocol.json", "protocol_sha256": "a" * 64,
                        "source_partitions": ["train"],
                        "files_read": {"path": "files.json", "sha256": "a" * 64}},
        "pages": [{"id": "p1", "path": "pages/p1.json", "sha256": "a" * 64,
                   "source_group_ids": ["body"]}],
        "artifacts": [],
        "extensions": {"mf:import_report": {"path": REPORT, "sha256": sha256(tmp_path / REPORT)}},
    }
    if request.param:
        manifest["extensions"]["mf:partition"] = {
            "version": "1", "name": "train", "path": "provenance/partition.json",
            "sha256": "a" * 64, "source_catalog_path": SOURCE,
            "source_catalog_sha256": sha256(tmp_path / SOURCE),
        }
    write_json(tmp_path / "manifest.json", manifest)
    reseal(tmp_path)
    return tmp_path


def reseal(root):
    """Refresh every receipt/metadata digest after intentional corruption."""
    manifest = load_json(root / "manifest.json")
    manifest["extensions"]["mf:import_report"]["sha256"] = sha256(root / REPORT)
    if "mf:partition" in manifest["extensions"]:
        manifest["extensions"]["mf:partition"]["source_catalog_sha256"] = sha256(root / SOURCE)
    manifest["artifacts"] = [
        {"path": relative, "sha256": sha256(root / relative), "role": "fixture"}
        for relative in (REPORT, CATALOG, SOURCE)
    ]
    write_json(root / "manifest.json", manifest)


def issues(root):
    return validate_import_receipt(root, load_json(root / "manifest.json"))


def test_receipt_matches_complete_source_catalog_without_reading_any_text(metadata_lot, monkeypatch):
    root = metadata_lot
    manifest = load_json(root / "manifest.json")
    # Warm schema caches before restricting reads to the declared metadata.
    assert validate_import_receipt(root, manifest) == []
    read_bytes, read_text = Path.read_bytes, Path.read_text
    opened = []

    def check(path):
        relative = path.relative_to(root).as_posix()
        assert relative in (REPORT, CATALOG, SOURCE)
        opened.append(relative)

    def guarded_bytes(path):
        check(path)
        return read_bytes(path)

    def guarded_text(path, *args, **kwargs):
        check(path)
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guarded_bytes)
    monkeypatch.setattr(Path, "read_text", guarded_text)
    assert validate_import_receipt(root, manifest) == []
    expected = SOURCE if "mf:partition" in manifest["extensions"] else CATALOG
    assert set(opened) == {REPORT, expected}


@pytest.mark.parametrize("field,value", [
    ("asset_id", "invented"), ("source_document_id", "invented"),
    ("source_group_id", "invented"), ("role", "title"), ("sha256", "0" * 64),
])
def test_rehashed_identity_changes_are_rejected(metadata_lot, field, value):
    report = load_json(metadata_lot / REPORT)
    report["accepted"][0][field] = value
    write_json(metadata_lot / REPORT, report)
    reseal(metadata_lot)
    errors = issues(metadata_lot)
    assert any("accepted entries differ" in error for error in errors), errors
    assert not any("SHA-256 mismatch" in error for error in errors)


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate"])
def test_accepted_is_an_exact_bijection(metadata_lot, change):
    report = load_json(metadata_lot / REPORT)
    if change == "missing":
        report["accepted"].pop()
    else:
        extra = deepcopy(report["accepted"][0])
        if change == "extra":
            extra.update(asset_id="invented", source_document_id="invented", sha256="0" * 64)
        report["accepted"].append(extra)
    write_json(metadata_lot / REPORT, report)
    reseal(metadata_lot)
    assert any("accepted entries differ" in error for error in issues(metadata_lot))


@pytest.mark.parametrize("field,value", [
    ("format", "other"), ("version", "2"), ("status", "fail"),
    ("accepted", None), ("accepted", []), ("accepted", [{"asset_id": "body"}]),
])
def test_rehashed_malformed_report_is_rejected(metadata_lot, field, value):
    report = load_json(metadata_lot / REPORT)
    report[field] = value
    write_json(metadata_lot / REPORT, report)
    reseal(metadata_lot)
    assert issues(metadata_lot)


@pytest.mark.parametrize("reference", [None, [], {}, {"path": "../report.json", "sha256": "a" * 64},
                                       {"path": REPORT, "sha256": "bad"},
                                       {"path": REPORT, "sha256": "a" * 64, "extra": 1}])
def test_malformed_reference_is_rejected(metadata_lot, reference):
    manifest = load_json(metadata_lot / "manifest.json")
    manifest["extensions"]["mf:import_report"] = reference
    assert validate_import_receipt(metadata_lot, manifest)


@pytest.mark.parametrize("tamper", ["reference", "artifact", "missing_artifact", "duplicate_artifact"])
def test_reference_and_artifact_hashes_must_match_bytes(metadata_lot, tamper):
    manifest = load_json(metadata_lot / "manifest.json")
    record = next(item for item in manifest["artifacts"] if item["path"] == REPORT)
    if tamper == "reference":
        manifest["extensions"]["mf:import_report"]["sha256"] = "0" * 64
    elif tamper == "artifact":
        record["sha256"] = "0" * 64
    elif tamper == "missing_artifact":
        manifest["artifacts"].remove(record)
    else:
        manifest["artifacts"].append(deepcopy(record))
    assert validate_import_receipt(metadata_lot, manifest)


def test_rehashed_duplicate_json_keys_fail(metadata_lot):
    raw = (metadata_lot / REPORT).read_text(encoding="utf-8")
    (metadata_lot / REPORT).write_text('{"version":"1",' + raw[1:], encoding="utf-8")
    reseal(metadata_lot)
    assert any("duplicate JSON key" in error for error in issues(metadata_lot))


def test_import_report_requires_catalog_030(metadata_lot):
    manifest = load_json(metadata_lot / "manifest.json")
    relative = SOURCE if "mf:partition" in manifest["extensions"] else CATALOG
    catalog = load_json(metadata_lot / relative)
    catalog["schema_version"] = "0.2.0"
    write_json(metadata_lot / relative, catalog)
    reseal(metadata_lot)
    assert any("source catalog schema_version 0.3.0" in error for error in issues(metadata_lot))


def test_dataset_runs_named_check_when_receipt_present(metadata_lot):
    # This metadata-only fixture intentionally lacks images/text. Its import
    # check is independent of those failures and is wired into the audit.
    checks = {item["name"]: item["status"]
              for item in validate_dataset(metadata_lot, verify_exports=False)["checks"]}
    assert checks["import_receipt"] == "pass"
    report = load_json(metadata_lot / REPORT)
    report["accepted"][0]["source_group_id"] = "forged"
    write_json(metadata_lot / REPORT, report)
    reseal(metadata_lot)
    checks = {item["name"]: item["status"]
              for item in validate_dataset(metadata_lot, verify_exports=False)["checks"]}
    assert checks["import_receipt"] == "fail"


def test_legacy_dataset_without_receipt_remains_valid(request):
    result = validate_dataset(request.getfixturevalue("legacy_dataset"), verify_exports=False)
    assert result["status"] == "pass", result["errors"]
    assert "import_receipt" not in {item["name"] for item in result["checks"]}
