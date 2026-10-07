"""Adversarial examples for geometry, ownership, provenance and file safety."""

from copy import deepcopy
import hashlib
import json
import struct
import zlib

from PIL import Image
import pytest

from mille_feuilles.validation import load_json, safe_path, validate_dataset, validate_page


def rect(left, top, right, bottom):
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


@pytest.fixture
def page():
    # The accent and ligature test code-point spans. Hyphenation crosses blocks.
    texts = ["Été disso-", "lution œuf"]
    lines, words = [], []
    for index, text in enumerate(texts):
        lid, bid = f"l{index}", f"b{index}"
        top = 10 + index * 30
        tokens = text.split(" ")
        position = 0
        word_ids = []
        for j, token in enumerate(tokens):
            wid = f"w{index}_{j}"
            word_ids.append(wid)
            hyphen = None
            if (index, j) in ((0, 1), (1, 0)):
                hyphen = {
                    "group_id": "h1",
                    "part": "start" if index == 0 else "end",
                    "reconstructed_text": "dissolution",
                }
            words.append(
                {
                    "id": wid,
                    "line_id": lid,
                    "polygon": rect(10 + j * 35, top, 40 + j * 35, top + 15),
                    "text": token,
                    "char_span": [position, position + len(token)],
                    "legibility": "readable",
                    "hyphenation": hyphen,
                }
            )
            position += len(token) + 1
        lines.append(
            {
                "id": lid,
                "block_id": bid,
                "polygon": rect(10, top, 90, top + 15),
                "baseline": [[10, top + 12], [90, top + 12]],
                "text": text,
                "word_ids": word_ids,
                "legibility": "readable",
            }
        )
    return {
        "schema_version": "0.2.0",
        "page_id": "p1",
        "profile": "fr_press_19c_columns_4_6",
        "image": {
            "path": "images/p1.png",
            "sha256": "a" * 64,
            "width": 100,
            "height": 100,
            "color_mode": "L",
            "dpi": 150,
        },
        "language": "fr",
        "provenance": {
            "seed": 42,
            "template_id": "template_press_v1",
            "asset_ids": ["text1", "template_press_v1"],
            "text_spans": [
                {"asset_id": "text1", "start": 0, "end": 19, "source_document_id": "original:demo"}
            ],
            "parameters": {"columns": 4, "render_dpi": 150},
        },
        "transforms": [],
        "articles": [{"id": "a1", "block_ids": ["b0", "b1"]}],
        "blocks": [
            {
                "id": f"b{i}",
                "category": "texte",
                "polygon": rect(5, 5 + i * 30, 95, 30 + i * 30),
                "article_id": "a1",
                "line_ids": [f"l{i}"],
            }
            for i in range(2)
        ]
        + [
            {
                "id": "sep",
                "category": "separateur",
                "polygon": rect(5, 80, 95, 81),
                "article_id": None,
                "line_ids": [],
            }
        ],
        "lines": lines,
        "words": words,
        "reading_order": {
            "block_ids": ["b0", "b1"],
            "unordered_block_ids": ["sep"],
            "line_ids": ["l0", "l1"],
        },
    }


def test_unicode_and_hyphenation_across_blocks_are_valid(page):
    assert validate_page(page) == []


@pytest.mark.parametrize(
    "mutate,fragment",
    [
        (lambda p: p["words"][0].update(char_span=[0, 4]), "span differs"),
        (lambda p: p["words"][1].update(char_span=[2, 9]), "overlapping"),
        (lambda p: p["words"][0].update(id="b0"), "duplicate id"),
        (lambda p: p["lines"][0].update(block_id="missing"), "line ownership"),
        (lambda p: p["blocks"][0].update(article_id="missing"), "article reference"),
        (lambda p: p["blocks"][2].update(article_id="a1"), "separator must"),
        (
            lambda p: p["blocks"][0].update(category="annonce", article_id=None),
            "advertisement requires",
        ),
        (lambda p: p["words"][0].update(polygon=rect(70, 60, 90, 70)), "word outside line"),
        (lambda p: p["lines"][0].update(baseline=[[10, 60], [90, 60]]), "baseline outside"),
        (lambda p: p["lines"][0].update(baseline=[[90, 22], [10, 22]]), "left-to-right"),
        (
            lambda p: p["blocks"][0].update(polygon=list(reversed(p["blocks"][0]["polygon"]))),
            "signed area",
        ),
        (lambda p: p["blocks"][0].update(polygon=[[0, 0], [90, 30], [90, 0], [0, 30]]), "simple"),
        (lambda p: p["reading_order"]["block_ids"].append("sep"), "exactly the textual"),
        (lambda p: p["reading_order"].update(line_ids=["l1", "l0"]), "concatenate"),
        (
            lambda p: p["words"][1]["hyphenation"].update(reconstructed_text="inventé"),
            "reconstructed",
        ),
        (lambda p: p["words"][2].update(hyphenation=None), "exactly one start"),
        (lambda p: p["words"][0].update(legibility="illegible"), "worst word"),
        (lambda p: p["lines"][0].update(text="Été\u200bdisso-"), "invisible control"),
        (lambda p: p["provenance"]["text_spans"][0].update(end=0), "reversed"),
        (lambda p: p.update(schema_version="0.1.0"), "0.2.0"),
        (lambda p: p.update(page_id="p1\n"), "does not match"),
        (lambda p: p["image"].update(width=True), "integer"),
        (lambda p: p["blocks"][0]["polygon"][0].__setitem__(0, float("nan")), "non-finite"),
        (
            lambda p: p["transforms"].append(
                {
                    "kind": "affine",
                    "parameters": {},
                    "geometry": {"matrix": [[1, 0, 0], [0, 0, 0], [0, 0, 1]]},
                }
            ),
            "non-singular",
        ),
    ],
)
def test_reject_semantic_violations(page, mutate, fragment):
    mutate(page)
    assert any(fragment in error for error in validate_page(page))


def test_article_must_be_contiguous(page):
    extra = deepcopy(page["blocks"][0])
    extra.update(id="other", article_id="article_other", line_ids=["other_line"])
    line = deepcopy(page["lines"][0])
    line.update(id="other_line", block_id="other", text="Été", word_ids=["other_word"])
    word = deepcopy(page["words"][0])
    word.update(id="other_word", line_id="other_line")
    page["blocks"].append(extra)
    page["lines"].append(line)
    page["words"].append(word)
    page["articles"].append({"id": "article_other", "block_ids": ["other"]})
    page["reading_order"]["block_ids"] = ["b0", "other", "b1"]
    page["reading_order"]["line_ids"] = ["l0", "other_line", "l1"]
    assert any("article blocks must be consecutive" in e for e in validate_page(page))


@pytest.mark.parametrize(
    "relative",
    ["../secret", "/etc/passwd", "a/../../secret", "a\\secret", "C:/secret", "a//b", "a/./b", ""],
)
def test_unsafe_paths_rejected(tmp_path, relative):
    with pytest.raises(ValueError):
        safe_path(tmp_path, relative)


def test_symlink_escape_rejected(tmp_path):
    (tmp_path / "outside").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        safe_path(tmp_path, "outside/secret")


def test_symlink_loop_rejected(tmp_path):
    (tmp_path / "loop").symlink_to("loop")
    with pytest.raises(ValueError, match="cannot resolve"):
        safe_path(tmp_path, "loop")


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e309}'])
def test_strict_json(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        load_json(path)


@pytest.fixture
def dataset(tmp_path, page):
    def write(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def raw(name, content):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    text = raw("assets/text.txt", "Été dissolution œuf. Texte original.")
    template = write("assets/template.json", {"columns": 4})
    font = raw("assets/font.ttf", "font payload is not interpreted by the dataset validator")
    font_license = raw("assets/OFL.txt", "fixture font license evidence")
    text_notice = raw("assets/NOTICE.md", "fixture original text rights notice")
    rights = {
        "status": "verified",
        "license": "CC0-1.0",
        "evidence_uri": "https://example.org/rights",
        "attribution": "fixture",
        "redistribution_allowed": True,
    }
    registry = write(
        "assets.json",
        {
            "schema_version": "0.2.0",
            "assets": [
                {
                    "id": "text1",
                    "kind": "text",
                    **text,
                    "source_uri": "original:demo",
                    "rights": {**rights, "evidence_uri": text_notice["path"]},
                    "metadata": {
                        "source_document_id": "original:demo",
                        "evidence_files": [text_notice],
                    },
                },
                {
                    "id": "template_press_v1",
                    "kind": "template",
                    **template,
                    "source_uri": "original:template",
                    "rights": rights,
                    "metadata": {},
                },
                {
                    "id": "font_fixture",
                    "kind": "font",
                    **font,
                    "source_uri": "original:font",
                    "rights": rights,
                    "metadata": {"evidence_files": [font_license]},
                },
            ],
        },
    )
    config = write("config.json", {"columns": 4})
    environment = write("environment.json", {"python": "test"})
    protocol = raw("calibration/protocol.md", "train/dev only")
    files = raw("calibration/files.tsv", "path\tsha256\n")
    (tmp_path / "images").mkdir()
    Image.new("L", (100, 100), 255).save(tmp_path / page["image"]["path"], dpi=(150, 150))
    page["image"]["sha256"] = hashlib.sha256(
        (tmp_path / page["image"]["path"]).read_bytes()
    ).hexdigest()
    page_ref = write("pages/p1.json", page)
    qa_path = tmp_path / "qa/p1.png"
    qa_path.parent.mkdir()
    Image.new("RGB", (100, 100), "white").save(qa_path)
    qa = {"path": "qa/p1.png", "sha256": hashlib.sha256(qa_path.read_bytes()).hexdigest()}
    artifacts = [
        {**r, "role": "fixture"}
        for r in (
            text,
            template,
            font,
            font_license,
            text_notice,
            registry,
            config,
            environment,
            protocol,
            files,
            qa,
            {"path": page["image"]["path"], "sha256": page["image"]["sha256"]},
        )
    ]
    manifest = {
        "schema_version": "0.2.0",
        "dataset_id": "test_dataset",
        "profile": page["profile"],
        "generator": {
            "commit": "a" * 40,
            "dirty": False,
            "environment_path": environment["path"],
            "environment_sha256": environment["sha256"],
        },
        "config": config,
        "rng": {"algorithm": "PCG64", "version": "1", "seed": 42},
        "assets": registry,
        "calibration": {
            "protocol_path": protocol["path"],
            "protocol_sha256": protocol["sha256"],
            "source_partitions": ["train", "dev"],
            "files_read": files,
        },
        "pages": [{"id": "p1", **page_ref, "source_group_ids": ["original:demo"]}],
        "artifacts": artifacts,
    }
    write("manifest.json", manifest)
    return tmp_path


def test_valid_dataset_hashes_and_unicode_sources(dataset):
    result = validate_dataset(dataset, verify_exports=False)
    assert result["status"] == "pass", result["errors"]
    assert result["checks"][-1]["status"] == "not_run"


def test_rehashed_source_span_must_occur_in_composed_text(dataset):
    page_path = dataset / "pages/p1.json"
    page = load_json(page_path)
    # A different, in-bounds segment of the same verified source document.
    source = (dataset / "assets/text.txt").read_text(encoding="utf-8")
    page["provenance"]["text_spans"][0].update(start=source.index("Texte"), end=len(source))
    assert validate_page(page) == []
    page_path.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
    manifest = load_json(dataset / "manifest.json")
    manifest["pages"][0]["sha256"] = hashlib.sha256(page_path.read_bytes()).hexdigest()
    (dataset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = validate_dataset(dataset, verify_exports=False)
    assert result["status"] == "fail"
    assert any("source segment not found" in error for error in result["errors"])


def test_tamper_detected(dataset):
    (dataset / "assets/text.txt").write_text("altered")
    result = validate_dataset(dataset, verify_exports=False)
    assert result["status"] == "fail"
    assert any("SHA-256 mismatch" in e for e in result["errors"])


def test_rehashed_dimensions_still_detected(dataset):
    path = dataset / "pages/p1.json"
    page = load_json(path)
    page["image"]["width"] = 101
    path.write_text(json.dumps(page))
    manifest = load_json(dataset / "manifest.json")
    manifest["pages"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    result = validate_dataset(dataset, verify_exports=False)
    assert any("actual PNG dimensions" in e for e in result["errors"])


def test_rehashed_provenance_still_detected(dataset):
    path = dataset / "pages/p1.json"
    page = load_json(path)
    page["provenance"]["text_spans"][0]["source_document_id"] = "foreign:document"
    path.write_text(json.dumps(page))
    manifest = load_json(dataset / "manifest.json")
    manifest["pages"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    result = validate_dataset(dataset, verify_exports=False)
    assert any("source_document_id differs" in e for e in result["errors"])
    assert any("source_group_ids omit" in e for e in result["errors"])


def test_calibration_test_partition_rejected(dataset):
    path = dataset / "manifest.json"
    manifest = load_json(path)
    manifest["calibration"]["source_partitions"].append("test")
    path.write_text(json.dumps(manifest))
    assert validate_dataset(dataset, verify_exports=False)["status"] == "fail"


def test_duplicate_key_in_dataset_rejected_without_crash(dataset):
    (dataset / "manifest.json").write_text('{"schema_version":"0.2.0", "schema_version":"0.2.0"}')
    result = validate_dataset(dataset)
    assert result["status"] == "fail"
    assert "duplicate JSON key" in result["errors"][0]


def test_dataset_symlink_image_escape_rejected(dataset):
    image = dataset / "images/p1.png"
    image.unlink()
    image.symlink_to(dataset.parent / "private.png")
    result = validate_dataset(dataset, verify_exports=False)
    assert result["status"] == "fail"
    assert any("escapes dataset" in e for e in result["errors"])


def test_rehashed_config_duplicate_key_rejected(dataset):
    path = dataset / "config.json"
    path.write_text('{"columns":4,"columns":6}')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = load_json(dataset / "manifest.json")
    manifest["config"]["sha256"] = digest
    for artifact in manifest["artifacts"]:
        if artifact["path"] == "config.json":
            artifact["sha256"] = digest
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    result = validate_dataset(dataset, verify_exports=False)
    assert any("duplicate JSON key" in e for e in result["errors"])


def test_missing_exports_are_release_failure(dataset):
    result = validate_dataset(dataset)
    assert result["status"] == "fail"
    assert any("missing export artifact" in e for e in result["errors"])


def test_nonreadable_is_representable_but_not_a_pilot_delivery(dataset):
    path = dataset / "pages/p1.json"
    page = load_json(path)
    page["words"][0]["legibility"] = "uncertain"
    page["lines"][0]["legibility"] = "uncertain"
    assert validate_page(page) == []
    path.write_text(json.dumps(page))
    manifest = load_json(dataset / "manifest.json")
    manifest["pages"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    result = validate_dataset(dataset, verify_exports=False)
    assert any("pilot profile excludes" in e for e in result["errors"])


def rehash_fixture_file(dataset, relative):
    """Model a self-consistent manifest mutation, not merely stale bytes."""
    digest = hashlib.sha256((dataset / relative).read_bytes()).hexdigest()
    manifest = load_json(dataset / "manifest.json")
    for record in manifest["artifacts"]:
        if record["path"] == relative:
            record["sha256"] = digest
    if manifest["assets"]["path"] == relative:
        manifest["assets"]["sha256"] = digest
    (dataset / "manifest.json").write_text(json.dumps(manifest))


def remove_fixture_inventory_entry(dataset, relative):
    manifest = load_json(dataset / "manifest.json")
    manifest["artifacts"] = [r for r in manifest["artifacts"] if r["path"] != relative]
    (dataset / "manifest.json").write_text(json.dumps(manifest))


@pytest.mark.parametrize("remove_file", [True, False])
def test_qa_cannot_be_omitted_from_manifest(dataset, remove_file):
    relative = "qa/p1.png"
    if remove_file:
        (dataset / relative).unlink()
    remove_fixture_inventory_entry(dataset, relative)
    result = validate_dataset(dataset, verify_exports=False)
    assert result["status"] == "fail"
    assert any("missing QA artifact" in error for error in result["errors"])


@pytest.mark.parametrize("dimensions", [(1, 1), (200, 200), (100, 50)])
def test_rehashed_unusable_qa_dimensions_are_rejected(dataset, dimensions):
    Image.new("RGB", dimensions).save(dataset / "qa/p1.png")
    rehash_fixture_file(dataset, "qa/p1.png")
    result = validate_dataset(dataset, verify_exports=False)
    assert any("QA overlay dimensions/aspect" in error for error in result["errors"])


def test_rehashed_jpeg_with_png_name_is_not_a_qa_png(dataset):
    Image.new("RGB", (100, 100)).save(dataset / "qa/p1.png", format="JPEG")
    rehash_fixture_file(dataset, "qa/p1.png")
    result = validate_dataset(dataset, verify_exports=False)
    assert any("QA overlay is not a PNG" in error for error in result["errors"])


def test_rehashed_nonimage_qa_is_rejected(dataset):
    (dataset / "qa/p1.png").write_text("not a PNG")
    rehash_fixture_file(dataset, "qa/p1.png")
    result = validate_dataset(dataset, verify_exports=False)
    assert any("invalid QA overlay" in error for error in result["errors"])


def test_qa_declaring_extreme_dimensions_returns_failure_without_allocating_it(dataset):
    path = dataset / "qa/p1.png"
    data = bytearray(path.read_bytes())
    assert data[12:16] == b"IHDR"
    data[16:24] = struct.pack(">II", 1_000_000, 1_000_000)
    data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]) & 0xFFFFFFFF)
    path.write_bytes(data)
    rehash_fixture_file(dataset, "qa/p1.png")
    result = validate_dataset(dataset, verify_exports=False)
    assert result["status"] == "fail"
    assert any("invalid QA overlay" in error for error in result["errors"])


@pytest.mark.parametrize("relative", ["assets/OFL.txt", "assets/NOTICE.md"])
def test_rights_evidence_cannot_disappear_with_its_manifest_entry(dataset, relative):
    (dataset / relative).unlink()
    remove_fixture_inventory_entry(dataset, relative)
    result = validate_dataset(dataset, verify_exports=False)
    assert result["status"] == "fail"
    assert any(f"missing evidence artifact: {relative}" in error for error in result["errors"])
    assert any(relative in error and "cannot verify" in error for error in result["errors"])


def test_font_license_hash_is_checked_against_declared_evidence(dataset):
    (dataset / "assets/OFL.txt").write_text("modified licence bytes")
    rehash_fixture_file(dataset, "assets/OFL.txt")
    result = validate_dataset(dataset, verify_exports=False)
    assert any("SHA-256 mismatch: assets/OFL.txt" in error for error in result["errors"])
    checks = {check["name"]: check["status"] for check in result["checks"]}
    assert checks["file_hashes"] == "pass"
    assert checks["assets"] == "fail"


def test_local_rights_notice_is_required_without_repeated_evidence_metadata(dataset):
    registry_path = dataset / "assets.json"
    registry = load_json(registry_path)
    registry["assets"][0]["metadata"].pop("evidence_files")
    registry_path.write_text(json.dumps(registry))
    rehash_fixture_file(dataset, "assets.json")
    assert validate_dataset(dataset, verify_exports=False)["status"] == "pass"
    (dataset / "assets/NOTICE.md").unlink()
    remove_fixture_inventory_entry(dataset, "assets/NOTICE.md")
    result = validate_dataset(dataset, verify_exports=False)
    assert any("missing local rights evidence" in error for error in result["errors"])


@pytest.mark.parametrize(
    "evidence", [None, {}, [None], [{"path": "x"}], [{"path": "x", "sha256": 3}]]
)
def test_malformed_evidence_metadata_returns_failure(dataset, evidence):
    registry_path = dataset / "assets.json"
    registry = load_json(registry_path)
    registry["assets"][-1]["metadata"]["evidence_files"] = evidence
    registry_path.write_text(json.dumps(registry))
    rehash_fixture_file(dataset, "assets.json")
    result = validate_dataset(dataset, verify_exports=False)
    assert any("evidence_files" in error for error in result["errors"])


def test_evidence_path_cannot_escape_dataset(dataset):
    registry_path = dataset / "assets.json"
    registry = load_json(registry_path)
    registry["assets"][-1]["metadata"]["evidence_files"][0]["path"] = "../external-license.txt"
    registry_path.write_text(json.dumps(registry))
    rehash_fixture_file(dataset, "assets.json")
    result = validate_dataset(dataset, verify_exports=False)
    assert any("unsafe relative path" in error for error in result["errors"])
