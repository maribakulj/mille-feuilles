"""Version 0.3 binds every corpus block to its precise source occurrence."""

from copy import deepcopy
import hashlib
import json

from PIL import Image
import pytest

from mille_feuilles.validation import validate_dataset, validate_page, validate_text_provenance


TEXTS = {"body": "Été dissolution œuf.", "title": "Débat local"}
LITERAL = ["MILLE FEUILLES", "Journal synthétique"]


def rect(left, top, right, bottom):
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


def source_span(asset, article, blocks):
    return {
        "asset_id": asset,
        "start": 0,
        "end": len(TEXTS[asset]),
        "source_document_id": f"document_{asset}",
        "article_id": article,
        "block_ids": blocks,
    }


@pytest.fixture
def page():
    result = {
        "schema_version": "0.3.0",
        "page_id": "p1",
        "profile": "fr_press_19c_columns_4_6",
        "image": {
            "path": "images/p1.png", "sha256": "a" * 64,
            "width": 512, "height": 512, "color_mode": "L", "dpi": 150,
        },
        "language": "fr",
        "provenance": {
            "seed": 1, "template_id": "template", "asset_ids": ["template", "body", "title"],
            "text_spans": [
                source_span("title", "a1", ["b2"]),
                source_span("body", "a1", ["b3", "b4"]),
                source_span("body", "a2", ["b5"]),
            ],
            "parameters": {"columns": 4, "render_dpi": 150},
            "extensions": {"mf:template_article_ids": ["header"]},
        },
        "transforms": [], "articles": [], "blocks": [], "lines": [], "words": [],
        "reading_order": {"block_ids": [], "unordered_block_ids": [], "line_ids": []},
    }
    content = [
        ("header", LITERAL),
        ("a1", [TEXTS["title"], "Été disso-", "lution œuf."]),
        ("a2", [TEXTS["body"]]),
    ]
    for aid, block_texts in content:
        article = {"id": aid, "block_ids": []}
        result["articles"].append(article)
        for text in block_texts:
            index = len(result["blocks"])
            bid, lid = f"b{index}", f"l{index}"
            top = 10 + index * 30
            article["block_ids"].append(bid)
            result["blocks"].append({
                "id": bid, "category": "titre" if index in (0, 2) else "texte",
                "polygon": rect(5, top - 2, 505, top + 22), "article_id": aid, "line_ids": [lid],
            })
            line = {
                "id": lid, "block_id": bid, "polygon": rect(10, top, 500, top + 20),
                "baseline": [[10, top + 16], [500, top + 16]], "text": text,
                "word_ids": [], "legibility": "readable",
            }
            result["lines"].append(line)
            cursor, x = 0, 10
            for token in text.split():
                wid = f"w{len(result['words'])}"
                hyphen = None
                if token in ("disso-", "lution"):
                    hyphen = {"group_id": "hyp1", "part": "start" if token == "disso-" else "end",
                              "reconstructed_text": "dissolution"}
                result["words"].append({
                    "id": wid, "line_id": lid, "text": token,
                    "char_span": [cursor, cursor + len(token)],
                    "polygon": rect(x, top, x + 8 * len(token), top + 20),
                    "legibility": "readable", "hyphenation": hyphen,
                })
                line["word_ids"].append(wid)
                cursor += len(token) + 1
                x += 8 * (len(token) + 1)
            result["reading_order"]["block_ids"].append(bid)
            result["reading_order"]["line_ids"].append(lid)
    return result


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def dataset(tmp_path, page):
    rights = {"status": "verified", "license": "CC0-1.0", "attribution": "test fixture",
              "evidence_uri": "https://example.org/fixture", "redistribution_allowed": True}
    assets = []
    for asset_id, content in {**TEXTS, "template": "fixture template"}.items():
        relative = f"assets/{asset_id}.txt"
        path = tmp_path / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8")
        metadata = ({"literal_text": LITERAL} if asset_id == "template" else {
            "source_document_id": f"document_{asset_id}", "source_group_id": f"group_{asset_id}",
        })
        assets.append({"id": asset_id, "kind": "template" if asset_id == "template" else "text",
                       "path": relative, "sha256": digest(path), "source_uri": "original:fixture",
                       "rights": rights, "metadata": metadata})
    write_json(tmp_path / "assets.json", {"schema_version": "0.2.0", "assets": assets})
    for name in ("config.json", "environment.json", "calibration.json", "files.json"):
        write_json(tmp_path / name, {})
    for relative in ("images/p1.png", "qa/p1.png"):
        path = tmp_path / relative
        path.parent.mkdir(exist_ok=True)
        Image.new("L", (512, 512), 255).save(path, dpi=(150, 150))
    page["image"]["sha256"] = digest(tmp_path / page["image"]["path"])
    write_json(tmp_path / "pages/p1.json", page)

    def reference(name):
        return {"path": name, "sha256": digest(tmp_path / name)}

    manifest = {
        "schema_version": "0.3.0", "dataset_id": "test_v3", "profile": page["profile"],
        "generator": {"commit": "a" * 40, "dirty": False, "environment_path": "environment.json",
                      "environment_sha256": digest(tmp_path / "environment.json")},
        "config": reference("config.json"), "assets": reference("assets.json"),
        "rng": {"algorithm": "fixture", "version": "1", "seed": 1},
        "calibration": {"protocol_path": "calibration.json",
                        "protocol_sha256": digest(tmp_path / "calibration.json"),
                        "source_partitions": ["train", "dev"], "files_read": reference("files.json")},
        "pages": [{"id": "p1", **reference("pages/p1.json"),
                   "source_group_ids": ["group_body", "group_title"]}],
        "artifacts": [{**reference(path.relative_to(tmp_path).as_posix()), "role": "fixture"}
                      for path in sorted(tmp_path.rglob("*")) if path.is_file()],
    }
    write_json(tmp_path / "manifest.json", manifest)
    return tmp_path


def reseal(root):
    """Refresh declared hashes so semantic corruption cannot hide behind a hash failure."""
    manifest = json.loads((root / "manifest.json").read_text())
    for ref in [manifest["assets"], *manifest["pages"], *manifest["artifacts"]]:
        ref["sha256"] = digest(root / ref["path"])
    write_json(root / "manifest.json", manifest)


def test_bound_multiblock_hyphenation_and_shared_source_pass(page, dataset):
    assert validate_page(page) == []
    assert validate_text_provenance(page, TEXTS) == []
    assert validate_dataset(dataset, verify_exports=False)["errors"] == []


@pytest.mark.parametrize("field", ["article_id", "block_ids"])
def test_v3_requires_explicit_span_binding(page, field):
    del page["provenance"]["text_spans"][0][field]
    assert any(field in error for error in validate_page(page))


@pytest.mark.parametrize("mutate,fragment", [
    (lambda p: p["provenance"]["text_spans"][0].update(article_id="a2"), "binding"),
    (lambda p: p["provenance"]["text_spans"][1]["block_ids"].reverse(), "article order"),
    (lambda p: p["provenance"]["text_spans"].pop(), "exactly one provenance owner"),
    (lambda p: p["provenance"]["text_spans"].append(
        deepcopy(p["provenance"]["text_spans"][0])), "exactly one provenance owner"),
    (lambda p: p["provenance"]["extensions"].update(
        {"mf:template_article_ids": ["header", "a1"]}), "exactly one provenance owner"),
    (lambda p: p["provenance"]["extensions"].update(
        {"mf:template_article_ids": ["missing"]}), "unknown template article"),
    (lambda p: p["provenance"]["extensions"].update(
        {"mf:template_article_ids": ["header", "header"]}), "non-unique"),
    (lambda p: p["provenance"]["extensions"].update(
        {"mf:template_article_ids": "header"}), "array"),
])
def test_invalid_coverage_and_ownership_fail(page, mutate, fragment):
    mutate(page)
    assert any(fragment in error for error in validate_page(page))


def test_hyphenation_cannot_cross_two_source_spans(page):
    original = page["provenance"]["text_spans"][1]
    original["block_ids"] = ["b3"]
    page["provenance"]["text_spans"].append({**original, "block_ids": ["b4"]})
    assert any("hyphenation crosses" in error for error in validate_page(page))


def test_correct_other_article_cannot_mask_mutated_bound_article(page):
    word = next(w for w in page["words"] if w["line_id"] == "l5" and w["text"] == "œuf.")
    word["text"] = "œil."
    page["lines"][5]["text"] = page["lines"][5]["text"].replace("œuf.", "œil.")
    assert validate_page(page) == []
    assert any("exact bound block text" in error for error in validate_text_provenance(page, TEXTS))
    # The old occurrence contract deliberately still accepts this ambiguous attribution.
    page["schema_version"] = "0.2.0"
    for span in page["provenance"]["text_spans"]:
        del span["article_id"], span["block_ids"]
    assert validate_page(page) == []
    assert validate_text_provenance(page, TEXTS) == []


def test_substring_is_insufficient_for_bound_blocks(page):
    page["provenance"]["text_spans"][2]["end"] = len("Été")
    assert validate_page(page) == []
    assert validate_text_provenance(page, TEXTS)


def test_source_whitespace_and_nfd_are_normalized_without_changing_punctuation(page):
    texts = {**TEXTS, "title": "De\u0301bat\n  local"}
    page["provenance"]["text_spans"][0]["end"] = len(texts["title"])
    assert validate_text_provenance(page, texts) == []
    assert validate_text_provenance(page, {**texts, "body": "Été dissolution œuf!"})


def test_storage_order_does_not_change_bound_source_text(page):
    for key in ("articles", "blocks", "lines", "words"):
        page[key].reverse()
    page["provenance"]["text_spans"].reverse()
    assert validate_page(page) == []
    assert validate_text_provenance(page, TEXTS) == []


def test_unused_declared_text_asset_does_not_add_a_page_source_group(dataset):
    path = dataset / "assets.json"
    registry = json.loads(path.read_text())
    unused = deepcopy(registry["assets"][0])
    unused["id"] = "unused"
    unused["metadata"].update(source_document_id="unused_document", source_group_id="unused_group")
    registry["assets"].append(unused)
    write_json(path, registry)
    path = dataset / "pages/p1.json"
    page = json.loads(path.read_text())
    page["provenance"]["asset_ids"].append("unused")
    write_json(path, page)
    reseal(dataset)
    assert validate_dataset(dataset, verify_exports=False)["errors"] == []


@pytest.mark.parametrize("groups", [["document_body", "document_title"], ["group_body"],
                                   ["group_body", "group_title", "unused_group"]])
def test_group_set_must_equal_used_asset_groups(dataset, groups):
    path = dataset / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["pages"][0]["source_group_ids"] = groups
    write_json(path, manifest)
    result = validate_dataset(dataset, verify_exports=False)
    assert any("exact used source groups" in error for error in result["errors"])


@pytest.mark.parametrize("change,fragment", [
    (lambda assets: assets[0]["metadata"].pop("source_group_id"), "missing source_group_id"),
    (lambda assets: assets[0]["metadata"].update(source_document_id="wrong"),
     "source_document_id differs"),
    (lambda assets: assets[2]["metadata"].update(literal_text=["Different masthead"]),
     "exact template"),
    (lambda assets: assets[2]["metadata"].update(literal_text="MILLE FEUILLES"),
     "nonempty list"),
])
def test_rehashed_asset_metadata_cannot_bypass_provenance(dataset, change, fragment):
    path = dataset / "assets.json"
    registry = json.loads(path.read_text())
    change(registry["assets"])
    write_json(path, registry)
    reseal(dataset)
    result = validate_dataset(dataset, verify_exports=False)
    assert any(fragment in error for error in result["errors"])
    assert not any("SHA-256 mismatch" in error for error in result["errors"])


def test_falsely_exempted_body_must_match_literal_template(dataset):
    path = dataset / "pages/p1.json"
    page = json.loads(path.read_text())
    page["provenance"]["extensions"]["mf:template_article_ids"].append("a2")
    page["provenance"]["text_spans"].pop()
    assert validate_page(page) == []
    write_json(path, page)
    reseal(dataset)
    result = validate_dataset(dataset, verify_exports=False)
    assert any("exact template" in error for error in result["errors"])


def test_page_and_manifest_versions_cannot_disagree(dataset):
    path = dataset / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["schema_version"] = "0.2.0"
    write_json(path, manifest)
    result = validate_dataset(dataset, verify_exports=False)
    assert any("schema_version differs" in error for error in result["errors"])


def test_legacy_dataset_keeps_document_id_subset_semantics(dataset):
    path = dataset / "pages/p1.json"
    page = json.loads(path.read_text())
    page["schema_version"] = "0.2.0"
    for span in page["provenance"]["text_spans"]:
        del span["article_id"], span["block_ids"]
    write_json(path, page)
    path = dataset / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["schema_version"] = "0.2.0"
    manifest["pages"][0]["source_group_ids"] = ["document_body", "document_title", "legacy_extra"]
    write_json(path, manifest)
    reseal(dataset)
    assert validate_dataset(dataset, verify_exports=False)["errors"] == []
