"""External asset bundles: honest import, strict preflight and no overwrites."""

from copy import deepcopy
import json
import shutil

import pytest

from mille_feuilles import pipeline
from mille_feuilles.io import ROOT, sha256
from mille_feuilles.render import Config
from mille_feuilles.validation import load_json, validate_dataset


@pytest.fixture
def bundle(tmp_path):
    source = tmp_path / "source_bundle"
    shutil.copytree(ROOT / "assets", source / "assets")
    return source, load_json(source / "assets/catalog.json")


def write_catalog(source, catalog):
    (source / "assets/catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def text_asset(catalog, role="body"):
    return next(asset for asset in catalog["assets"]
                if asset["kind"] == "text" and asset["metadata"].get("role") == role)


def snapshot(root):
    return {path.relative_to(root).as_posix(): sha256(path)
            for path in root.rglob("*") if path.is_file()}


def reject_bundle(bundle, output):
    source, catalog = bundle
    write_catalog(source, catalog)
    before = snapshot(source)
    output.mkdir()
    with pytest.raises(ValueError):
        pipeline.prepare_assets(output, source)
    assert snapshot(source) == before, "Preflight must not rewrite the supplied bundle"
    assert not (output / "assets.json").exists(), "Rejected inputs cannot be accepted as assets"
    assert not (output / "manifest.json").exists()
    assert not (output / "images").exists()


def test_renamed_texts_are_selected_by_role_and_make_a_valid_self_contained_page(bundle, tmp_path):
    source, catalog = bundle
    renamed = {}
    for role, name in (("body", "chronique-originale.txt"),
                       ("title", "rubriques-originales.txt"),
                       ("advertisement", "avis-originaux.txt")):
        asset = text_asset(catalog, role)
        old_path = source / asset["path"]
        relative = f"assets/imported-texts/{name}"
        new_path = source / relative
        new_path.parent.mkdir(exist_ok=True)
        old_path.rename(new_path)
        asset["path"] = relative
        asset["sha256"] = sha256(new_path)
        asset["metadata"]["source_document_id"] = f"imported_demo_{role}"
        asset["metadata"]["preparation"] += " Import fixture: filename changed, bytes preserved."
        renamed[asset["id"]] = asset
    write_catalog(source, catalog)
    before = snapshot(source)
    output = tmp_path / "imported_lot"
    report = pipeline.build_dataset(
        output, Config(width=800, height=1100, columns=4, degradation="clean", seed=92),
        count=1, jobs=1, asset_source=source,
    )
    assert report["status"] == "pass", report["errors"]
    checked = validate_dataset(output)
    assert checked["status"] == "pass", checked["errors"]
    assert snapshot(source) == before
    assert (output / "assets/catalog.json").read_bytes() == (source / "assets/catalog.json").read_bytes()
    for asset in renamed.values():
        assert (output / asset["path"]).read_bytes() == (source / asset["path"]).read_bytes()
    page_path = next((output / "pages").glob("*.json"))
    page = load_json(page_path)
    assert page["words"]
    for span in page["provenance"]["text_spans"]:
        assert span["source_document_id"] == renamed[span["asset_id"]]["metadata"]["source_document_id"]
    # The output itself can serve as the asset bundle for a later reproduction.
    prepared_again = tmp_path / "prepared_from_lot"
    prepared_again.mkdir()
    reproduced_assets = pipeline.prepare_assets(prepared_again, output)
    assert {asset["id"] for asset in reproduced_assets} == {
        asset["id"] for asset in load_json(output / "assets.json")["assets"]
    }


def test_tampered_asset_hash_is_rejected(bundle, tmp_path):
    source, catalog = bundle
    asset = text_asset(catalog)
    path = source / asset["path"]
    path.write_text(path.read_text(encoding="utf-8") + "\nModification non déclarée.\n", encoding="utf-8")
    reject_bundle(bundle, tmp_path / "rejected")


def test_unresolved_rights_are_rejected(bundle, tmp_path):
    _, catalog = bundle
    text_asset(catalog)["rights"]["status"] = "unresolved"
    reject_bundle(bundle, tmp_path / "rejected")


@pytest.mark.parametrize("relative", ["../outside.txt", "/tmp/outside.txt", "assets/../../outside.txt"])
def test_asset_path_traversal_is_rejected_without_touching_outside(bundle, tmp_path, relative):
    _, catalog = bundle
    witness = tmp_path / "outside.txt"
    witness.write_text("user-owned witness", encoding="utf-8")
    original = witness.read_bytes()
    text_asset(catalog)["path"] = relative
    reject_bundle(bundle, tmp_path / "rejected")
    assert witness.read_bytes() == original


@pytest.mark.parametrize("malformed", [
    "assets/texts/NOTICE.md", ["assets/texts/NOTICE.md"],
    [{"path": "assets/texts/NOTICE.md"}], [{"sha256": "a" * 64}],
])
def test_malformed_evidence_files_raise_controlled_error(bundle, tmp_path, malformed):
    _, catalog = bundle
    text_asset(catalog)["metadata"]["evidence_files"] = malformed
    reject_bundle(bundle, tmp_path / "rejected")


def test_evidence_path_traversal_is_rejected(bundle, tmp_path):
    _, catalog = bundle
    text_asset(catalog)["metadata"]["evidence_files"][0]["path"] = "../notice.txt"
    reject_bundle(bundle, tmp_path / "rejected")


def test_tampered_evidence_hash_is_rejected(bundle, tmp_path):
    source, catalog = bundle
    evidence = text_asset(catalog)["metadata"]["evidence_files"][0]
    (source / evidence["path"]).write_text("Altered rights evidence.\n", encoding="utf-8")
    reject_bundle(bundle, tmp_path / "rejected")


def test_duplicate_text_role_is_rejected(bundle, tmp_path):
    _, catalog = bundle
    duplicate = deepcopy(text_asset(catalog))
    duplicate["id"] = "text_duplicate_body"
    duplicate["metadata"]["source_document_id"] = "other_document"
    catalog["assets"].append(duplicate)
    reject_bundle(bundle, tmp_path / "rejected")


def test_missing_text_role_is_rejected(bundle, tmp_path):
    _, catalog = bundle
    text_asset(catalog, "title")["metadata"].pop("role")
    reject_bundle(bundle, tmp_path / "rejected")


@pytest.mark.parametrize("empty", ["", " \n\n\t "])
def test_empty_or_whitespace_only_text_with_honest_hash_is_rejected(bundle, tmp_path, empty):
    source, catalog = bundle
    asset = text_asset(catalog)
    path = source / asset["path"]
    path.write_text(empty, encoding="utf-8")
    asset["sha256"] = sha256(path)
    reject_bundle(bundle, tmp_path / "rejected")


def test_existing_destination_is_not_overwritten_with_external_inputs(bundle, tmp_path):
    source, _ = bundle
    output = tmp_path / "existing"
    output.mkdir()
    witness = output / "personal-notes.txt"
    witness.write_bytes(b"keep this exact content\0\xff")
    before = snapshot(output)
    with pytest.raises(ValueError, match="non vide"):
        pipeline.build_dataset(output, Config(width=800, height=1100, columns=4),
                               count=1, asset_source=source)
    assert snapshot(output) == before
