"""Tiny orchestration fixtures, independent of the future NewsEye producer.

The source validator is stubbed ONLY for these hand-authored canonical/XML
fixtures, whose miniature source manifest intentionally lacks production assets.
The real canonical validator, pinned XSD and independent reader always run.
An additional negative test calls the real source validator. No render, corpus
or producer implementation is involved. Shared bundles are restored per test to
keep total scratch output below 5 MB; no production disk guard is bypassed.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from lxml import etree as ET
from PIL import Image
import pytest

from mille_feuilles import newseye_bundle as bundle
from mille_feuilles.validation import validate_dataset as real_validate_dataset

FIXTURES = bundle.ROOT / "tests/fixtures/newseye"
NS = {"p": bundle.PAGE_NS}
PASS = {"status": "pass", "errors": [], "checks": [
    {"name": name, "status": "pass", "detail": "simulated source validation fixture"}
    for name in ("manifest", "file_hashes", "strict_json_files", "unique_manifest_entries",
                 "manifest_coverage", "asset_registry", "partition_receipt", "assets",
                 "exports", "export_inventory")
]}
ENVIRONMENT = {"test_fixture": True, "projection_modules": {
    "newseye_bundle.py": "1" * 64, "newseye_reader.py": "2" * 64,
    "exports_newseye.py": "3" * 64,
}}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def miniature_source(root, ids=("p",), fixture="fixture-2-unicode-hyphen-geometry"):
    root.mkdir()
    (root / "images").mkdir()
    (root / "pages").mkdir()
    pages = []
    for identity in ids:
        # Renaming a frozen hand-authored fixture does not synthesize PAGE XML.
        raw = (FIXTURES / f"{fixture}.json").read_text().replace('"p"', f'"{identity}"')
        raw = raw.replace('"p_', f'"{identity}_').replace("images/p.png", f"images/{identity}.png")
        page = json.loads(raw)
        png = root / f"images/{identity}.png"
        Image.new("L", (400, 300), 255).save(png)
        page["image"]["sha256"] = digest(png.read_bytes())
        canonical = encode(page)
        (root / f"pages/{identity}.json").write_bytes(canonical)
        pages.append({"id": identity, "path": f"pages/{identity}.json", "sha256": digest(canonical), "source_group_ids": ["fixture"]})
    manifest = {
        "schema_version": "0.3.0", "dataset_id": "original_fixture",
        "profile": "fr_press_19c_columns_4_6",
        "generator": {"commit": "a" * 40, "dirty": False,
                      "environment_path": "environment.json", "environment_sha256": "0" * 64},
        "config": {"path": "config.json", "sha256": "0" * 64},
        "rng": {"algorithm": "fixture", "version": "1", "seed": 0},
        "assets": {"path": "assets.json", "sha256": "0" * 64},
        "calibration": {"protocol_path": "calibration.json", "protocol_sha256": "0" * 64,
                        "source_partitions": ["train"],
                        "files_read": {"path": "files-read.json", "sha256": "0" * 64}},
        "pages": pages,
        "artifacts": [{"path": page["path"], "sha256": page["sha256"], "role": "page"}
                      for page in pages],
    }
    (root / "manifest.json").write_bytes(encode(manifest))
    return root


def manual_projection(page, image_filename):
    identity = page["page_id"]
    fixture = "fixture-1-order" if len(page["blocks"]) == 6 else "fixture-2-unicode-hyphen-geometry"
    raw = (FIXTURES / f"{fixture}.expected.xml").read_text()
    raw = raw.replace("p_p\"", f"p_{identity}\"").replace("p_", f"{identity}_")
    # The pcGtsId prefix is literal p_, unlike canonical IDs embedded elsewhere.
    document = ET.fromstring(raw.encode())
    document.set("pcGtsId", f"p_{identity}")
    document.find("p:Page", NS).set("imageFilename", image_filename)
    mapping = {node.get("id"): node.get("id")[2:] for node in document.iter()
               if node.get("id", "")[:2] in {"r_", "a_", "s_", "g_", "l_", "w_"}}
    schema = read(bundle.ROOT / "schemas/newseye-report.schema.json")["properties"]
    report = {"format": "mille-feuilles-newseye-report", "version": "2", "profile": bundle.PROFILE,
              "page_id": identity, "image_filename": image_filename, "id_mapping": mapping,
              "not_represented": schema["not_represented"]["const"], "notes": schema["notes"]["const"]}
    return ET.tostring(document, encoding="UTF-8", xml_declaration=True), report


def source_pass(root):
    value = deepcopy(PASS)
    value["checks"].extend({"name": f"{prefix}:{page['id']}", "status": "pass", "detail": "fixture"}
                           for page in read(root / "manifest.json")["pages"]
                           for prefix in ("page", "page_files"))
    return value


@pytest.fixture
def orchestration(monkeypatch):
    calls = []

    def validated(root, *, verify_exports):
        assert verify_exports is True
        calls.append(root)
        return source_pass(root)

    monkeypatch.setattr(bundle, "validate_dataset", validated)
    monkeypatch.setattr(bundle, "_project", manual_projection)
    monkeypatch.setattr(bundle, "_projection_environment", lambda: deepcopy(ENVIRONMENT))
    monkeypatch.setattr(bundle, "git_state", lambda: ("a" * 40, False))
    return calls


@pytest.fixture(scope="module")
def archived(tmp_path_factory):
    root = tmp_path_factory.mktemp("newseye-small-archive")
    source = miniature_source(root / "source", ("p", "q"))
    target = root / "bundle"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(bundle, "validate_dataset", lambda root, *, verify_exports: source_pass(root))
        patch.setattr(bundle, "_project", manual_projection)
        patch.setattr(bundle, "_projection_environment", lambda: deepcopy(ENVIRONMENT))
        patch.setattr(bundle, "git_state", lambda: ("a" * 40, False))
        report = bundle.export_bundle(source, target, ["q", "p"])
    assert report["status"] == "pass", report
    return SimpleNamespace(root=target, source=source, report=report)


@pytest.fixture
def archive(archived):
    before = {path.relative_to(archived.root): path.read_bytes()
              for path in archived.root.rglob("*") if path.is_file()}
    yield archived
    # Restore only these test-owned small fixtures. Production never cleans up.
    for path in sorted(archived.root.rglob("*"), reverse=True):
        if path.is_symlink() or (path.is_file() and path.relative_to(archived.root) not in before):
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    for relative, data in before.items():
        path = archived.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            path.unlink()
        path.write_bytes(data)


def rehash(root, relative, data):
    (root / relative).write_bytes(data)
    manifest = read(root / "manifest.json")
    new_hash = digest(data)

    def update(value):
        if isinstance(value, dict):
            if value.get("path") == relative:
                value["sha256"] = new_hash
                if "size_bytes" in value:
                    value["size_bytes"] = len(data)
            for child in value.values():
                update(child)
        elif isinstance(value, list):
            for child in value:
                update(child)
    update(manifest)
    (root / "manifest.json").write_bytes(encode(manifest))


def mutation_errors(archive, relative, data):
    rehash(archive.root, relative, data)
    report = bundle.validate_bundle(archive.root)
    assert report["status"] == "fail", report
    assert not any(check["name"] == "inventory" and check["status"] == "fail"
                   for check in report["checks"]), report
    return "\n".join(report["errors"])


def test_raw_files_source_order_and_independent_portability(archive, monkeypatch):
    manifest = read(archive.root / "manifest.json")
    assert manifest["page_ids"] == ["p", "q"]
    assert [entry["source_index"] for entry in manifest["pages"]] == [0, 1]
    for identity in manifest["page_ids"]:
        assert (archive.root / f"images/{identity}.png").read_bytes() == (archive.source / f"images/{identity}.png").read_bytes()
        assert (archive.root / f"provenance/pages/{identity}.json").read_bytes() == (archive.source / f"pages/{identity}.json").read_bytes()
    assert (archive.root / "provenance/source-manifest.json").read_bytes() == (archive.source / "manifest.json").read_bytes()
    assert archive.report["source_unchanged"] is True
    assert archive.report["written_bytes"] < 500_000
    assert manifest["scope"]["external_reader"] == "not_evaluated"
    assert manifest["scope"]["source_rights_revalidated"] is False
    monkeypatch.setattr(bundle, "validate_dataset", lambda *args, **kwargs: pytest.fail("source validator used standalone"))
    monkeypatch.setattr(bundle, "_project", lambda *args, **kwargs: pytest.fail("producer used standalone"))
    renamed = archive.source.with_name("source-absent")
    archive.source.rename(renamed)
    try:
        assert bundle.validate_bundle(archive.root)["status"] == "pass"
    finally:
        renamed.rename(archive.source)


@pytest.mark.parametrize("selection", [[], ["missing"], ["p", "p"], "p", ["../p"], ["p\n"]])
def test_invalid_selection_no_creation(tmp_path, orchestration, selection):
    source = miniature_source(tmp_path / "source")
    with pytest.raises(ValueError):
        bundle.export_bundle(source, tmp_path / "output", selection)
    assert not (tmp_path / "output").exists()
    assert orchestration == [source.resolve()]


@pytest.mark.parametrize("kind", ["existing", "nested", "alias", "dangling", "same"])
def test_output_boundary_refused_without_validation(tmp_path, orchestration, kind):
    source = miniature_source(tmp_path / "source")
    output = tmp_path / "output"
    if kind == "existing":
        output.mkdir()
    elif kind == "nested":
        output = source / "new"
    elif kind == "alias":
        (tmp_path / "alias").symlink_to(source, target_is_directory=True)
        output = tmp_path / "alias/new"
    elif kind == "dangling":
        output.symlink_to(tmp_path / "absent")
    else:
        output = source
    before = bundle._source_snapshot(source)
    with pytest.raises(ValueError):
        bundle.export_bundle(source, output)
    assert not orchestration
    assert bundle._source_snapshot(source) == before
    if kind in {"nested", "alias"}:
        assert not output.exists()


@pytest.mark.parametrize("kind", ["fail", "not_run", "missing_export"])
def test_incomplete_source_validation_prevents_projection(tmp_path, orchestration, monkeypatch, kind):
    source = miniature_source(tmp_path / "source")
    report = deepcopy(PASS)
    if kind == "fail":
        report["status"] = "fail"
    elif kind == "not_run":
        report["checks"][0]["status"] = "not_run"
    else:
        report["checks"].pop()
    monkeypatch.setattr(bundle, "validate_dataset", lambda *args, **kwargs: report)
    monkeypatch.setattr(bundle, "_project", lambda *args: pytest.fail("projection must not run"))
    with pytest.raises(ValueError, match="complete validation"):
        bundle.export_bundle(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_real_source_validation_rejects_minimal_manifest(tmp_path):
    source = miniature_source(tmp_path / "source")
    assert real_validate_dataset(source, verify_exports=True)["status"] == "fail"
    with pytest.raises(ValueError, match="complete validation"):
        bundle.export_bundle(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("kind", ["pages", "bytes", "disk", "casefold"])
def test_resource_limits_preflight(tmp_path, orchestration, monkeypatch, kind):
    ids = ("p", "P") if kind == "casefold" else ("p", "q")
    source = miniature_source(tmp_path / "source", ids)
    if kind == "pages":
        monkeypatch.setattr(bundle, "MAX_PAGES", 1)
    elif kind == "bytes":
        monkeypatch.setattr(bundle, "MAX_BYTES", 500)
    elif kind == "disk":
        # Only simulate exhaustion; no test raises free space to bypass a guard.
        monkeypatch.setattr(bundle.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(ValueError):
        bundle.export_bundle(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_all_projections_before_first_write(tmp_path, orchestration, monkeypatch):
    source = miniature_source(tmp_path / "source", ("p", "q"))
    seen = []

    def project(page, filename):
        seen.append(page["page_id"])
        assert not (tmp_path / "output").exists()
        if page["page_id"] == "q":
            raise ValueError("unrepresentable fixture")
        return manual_projection(page, filename)
    monkeypatch.setattr(bundle, "_project", project)
    with pytest.raises(ValueError, match="unrepresentable"):
        bundle.export_bundle(source, tmp_path / "output")
    assert seen == ["p", "q"]
    assert not (tmp_path / "output").exists()


def test_source_change_before_write_refused(tmp_path, orchestration, monkeypatch):
    source = miniature_source(tmp_path / "source")

    def project(page, filename):
        (source / "new-evidence.txt").write_text("changed")
        return manual_projection(page, filename)
    monkeypatch.setattr(bundle, "_project", project)
    with pytest.raises(ValueError, match="Source changed during preflight"):
        bundle.export_bundle(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_partial_failure_preserved(tmp_path, orchestration, monkeypatch):
    source = miniature_source(tmp_path / "source")
    output = tmp_path / "output"
    original = Path.open

    def fail_png(self, mode="r", *args, **kwargs):
        if self == output / "images/p.png" and mode == "xb":
            raise OSError("simulated copy failure")
        return original(self, mode, *args, **kwargs)
    before = bundle._source_snapshot(source)
    monkeypatch.setattr(Path, "open", fail_png)
    with pytest.raises(OSError, match="simulated copy failure"):
        bundle.export_bundle(source, output)
    assert output.is_dir() and (output / "p.xml").is_file()
    assert not (output / "manifest.json").exists()
    assert bundle._source_snapshot(source) == before


@pytest.mark.parametrize("kind,expected", [
    ("article", "reading.text_regions_in_order"), ("line_text", "text"),
    ("word_text", "text"), ("word_polygon", "geometry"),
    ("middle_baseline", "geometry"), ("region_polygon", "geometry"),
    ("image_filename", "image"), ("type", "reading.text_regions_in_order"),
    ("word_order", "text"), ("word_membership", "text"),
])
def test_xml_semantics_rehashed_are_not_trusted(archive, kind, expected):
    document = ET.fromstring((archive.root / "p.xml").read_bytes())
    lines = document.findall(".//p:TextLine", NS)
    words = document.findall(".//p:Word", NS)
    region = document.find(".//p:TextRegion", NS)
    if kind == "article":
        lines[0].set("custom", lines[0].get("custom").replace("p_a0001", "p_other"))
    elif kind == "line_text":
        lines[0].find("p:TextEquiv/p:Unicode", NS).text = "Texte différent"
    elif kind == "word_text":
        words[0].find("p:TextEquiv/p:Unicode", NS).text = "Différent"
    elif kind == "word_polygon":
        words[0].find("p:Coords", NS).set("points", "11,10 70,10 70,30 10,30")
    elif kind == "middle_baseline":
        lines[-1].find("p:Baseline", NS).set("points", "10,82 80,83 150,82")
    elif kind == "region_polygon":
        region.find("p:Coords", NS).set("points", "9,10 326,10 326,30 9,30")
    elif kind == "image_filename":
        document.find("p:Page", NS).set("imageFilename", "images/missing.png")
    elif kind == "type":
        region.set("type", "paragraph")
        region.set("custom", region.get("custom").replace("heading", "paragraph"))
    elif kind == "word_order":
        first, second = words[:2]
        lines[0].remove(second)
        lines[0].insert(list(lines[0]).index(first), second)
    else:
        first = words[0]
        lines[0].remove(first)
        lines[-1].insert(2, first)
    assert expected in mutation_errors(archive, "p.xml", ET.tostring(document))


@pytest.mark.parametrize("kind", ["mapping_target", "mapping_domain", "loss", "notes", "page_id", "filename"])
def test_report_rehashed_is_checked_against_normative_schema(archive, kind):
    value = read(archive.root / "reports/p.json")
    if kind == "mapping_target":
        value["id_mapping"]["r_p_b0000"] = "p_wrong"
    elif kind == "mapping_domain":
        value["id_mapping"].pop("w_p_w000000")
    elif kind == "loss":
        value["not_represented"].pop()
    elif kind == "notes":
        value["notes"][0] = "Everything preserved."
    elif kind == "page_id":
        value["page_id"] = "q"
    else:
        value["image_filename"] = "images/q.png"
    assert "report" in mutation_errors(archive, "reports/p.json", encode(value))


@pytest.mark.parametrize("relative", ["schemas/page-2019-07-15.xsd", "schemas/PAGE-LICENSE", "schemas/provenance.json"])
def test_schema_provenance_rehashed_still_pinned(archive, relative):
    errors = mutation_errors(archive, relative, (archive.root / relative).read_bytes() + b"\n")
    assert "pinned schema provenance differs" in errors


@pytest.mark.parametrize("kind", ["extra", "directory", "symlink", "missing", "duplicate", "size", "path"])
def test_exact_confined_inventory(archive, tmp_path, kind):
    manifest = read(archive.root / "manifest.json")
    if kind == "extra":
        (archive.root / "extra.txt").write_text("not declared")
    elif kind == "directory":
        (archive.root / "empty").mkdir()
    elif kind == "symlink":
        external = tmp_path / "outside.txt"
        external.write_text("external")
        (archive.root / "external.txt").symlink_to(external)
    elif kind == "missing":
        (archive.root / "p.xml").unlink()
    elif kind == "duplicate":
        manifest["artifacts"].append(deepcopy(manifest["artifacts"][0]))
    elif kind == "size":
        manifest["artifacts"][0]["size_bytes"] += 1
    else:
        manifest["pages"][0]["xml"]["path"] = "../p.xml"
    (archive.root / "manifest.json").write_bytes(encode(manifest))
    assert bundle.validate_bundle(archive.root)["status"] == "fail"


def test_recorded_source_pass_cannot_omit_export_check(archive):
    value = read(archive.root / "provenance/source-validation.json")
    value["checks"] = [check for check in value["checks"] if check["name"] != "exports"]
    assert "export checks" in mutation_errors(archive, "provenance/source-validation.json", encode(value))


def test_projection_environment_requires_all_module_hashes(archive):
    value = read(archive.root / "provenance/environment.json")
    del value["projection_modules"]["newseye_reader.py"]
    assert "module hash" in mutation_errors(archive, "provenance/environment.json", encode(value))


def test_advertisement_separator_and_explicit_order_fixture(tmp_path, orchestration):
    source = miniature_source(tmp_path / "source", fixture="fixture-1-order")
    report = bundle.export_bundle(source, tmp_path / "bundle")
    assert report["status"] == "pass", report
    assert report["pages"] == 1


def test_canonical_rounding_matches_manual_fractional_geometry():
    page = read(FIXTURES / "fixture-2-unicode-hyphen-geometry.json")
    expected, _ = bundle._expectation(page, "images/p.png")
    manual = read(FIXTURES / "fixture-2-unicode-hyphen-geometry.expected-geometry.json")
    for key in ("regions", "lines", "words"):
        assert expected["geometry"][key] == manual[key]
    assert len(expected["geometry"]["lines"]["l_p_l00002"][1]) == 3


@pytest.mark.parametrize("value", [[], None, "invalid", {"dataset_id": "original_fixture", "pages": []}])
def test_malformed_archived_source_manifest_fails_cleanly(archive, value):
    assert "source_manifest_structure_only" in mutation_errors(
        archive, "provenance/source-manifest.json", encode(value),
    )


def memory_fixture():
    page = read(FIXTURES / "fixture-1-order.json")
    xml = ET.fromstring((FIXTURES / "fixture-1-order.expected.xml").read_bytes())
    schema = bundle._xml_schema((bundle.ROOT / "schemas/xml/page-2019-07-15.xsd").read_bytes())
    return page, xml, schema


def add_nontextual(page, xml, category, identity, points):
    page["blocks"].append({"id": identity, "category": category, "polygon": points,
                           "article_id": None, "line_ids": []})
    page["reading_order"]["unordered_block_ids"].append(identity)
    tag, prefix = ("SeparatorRegion", "s") if category == "separateur" else ("GraphicRegion", "g")
    region = ET.SubElement(xml.find("p:Page", NS), f"{{{bundle.PAGE_NS}}}{tag}", id=f"{prefix}_{identity}")
    ET.SubElement(region, f"{{{bundle.PAGE_NS}}}Coords", points=" ".join(f"{x},{y}" for x, y in points))
    return region


def test_nontextual_order_is_explicitly_lost_without_false_refusal():
    page, xml, schema = memory_fixture()
    add_nontextual(page, xml, "separateur", "p_b0006", [[380, 250], [382, 250], [382, 290], [380, 290]])
    page["reading_order"]["unordered_block_ids"].reverse()
    assert bundle.validate_page(page) == []
    issues, _ = bundle._projection_errors(ET.tostring(xml), page, "images/p.png", schema)
    assert issues == []


def test_graphic_cannot_become_an_advert_even_without_text_overlap():
    page, xml, schema = memory_fixture()
    region = add_nontextual(page, xml, "illustration", "p_b0006", [[380, 250], [395, 250], [395, 290], [380, 290]])
    assert bundle.validate_page(page) == []
    assert bundle._projection_errors(ET.tostring(xml), page, "images/p.png", schema)[0] == []
    region.tag = f"{{{bundle.PAGE_NS}}}AdvertRegion"
    issues, _ = bundle._projection_errors(ET.tostring(xml), page, "images/p.png", schema)
    assert issues == ["independent region_types differs from canonical"]


def test_homograph_order_cannot_hide_behind_text_or_geometry():
    page = read(FIXTURES / "fixture-2-unicode-hyphen-geometry.json")
    xml = ET.fromstring((FIXTURES / "fixture-2-unicode-hyphen-geometry.expected.xml").read_bytes())
    schema = bundle._xml_schema((bundle.ROOT / "schemas/xml/page-2019-07-15.xsd").read_bytes())
    words = xml.findall(".//p:TextLine", NS)[0].findall("p:Word", NS)
    page["words"][1]["text"] = page["words"][0]["text"]
    words[1].find("p:TextEquiv/p:Unicode", NS).text = page["words"][0]["text"]
    text = " ".join(word["text"] for word in page["words"][:8])
    page["lines"][0]["text"] = text
    position = 0
    for word in page["words"][:8]:
        word["char_span"] = [position, position + len(word["text"])]
        position += len(word["text"]) + 1
    region = xml.find(".//p:TextRegion", NS)
    line = region.find("p:TextLine", NS)
    line.find("p:TextEquiv/p:Unicode", NS).text = text
    region.find("p:TextEquiv/p:Unicode", NS).text = text
    assert bundle.validate_page(page) == []
    assert bundle._projection_errors(ET.tostring(xml), page, "images/p.png", schema)[0] == []
    line.remove(words[1])
    line.insert(list(line).index(words[0]), words[1])
    issues, _ = bundle._projection_errors(ET.tostring(xml), page, "images/p.png", schema)
    assert issues == ["independent word_ids_by_line differs from canonical"]


def test_degenerate_rounding_refused_before_geos_intersection():
    page, xml, schema = memory_fixture()
    page["blocks"][-1]["polygon"] = [[380.1, 250], [380.2, 250], [380.2, 290], [380.1, 290]]
    assert bundle.validate_page(page) == []
    with pytest.raises(ValueError, match="degenerates after integer rounding"):
        bundle._projection_errors(ET.tostring(xml), page, "images/p.png", schema)


@pytest.mark.parametrize("name", ["manifest", "assets", "page:p", "page_files:q"])
def test_source_validation_covers_all_original_pages_and_global_checks(archive, name):
    value = read(archive.root / "provenance/source-validation.json")
    value["checks"] = [check for check in value["checks"] if check["name"] != name]
    assert name in mutation_errors(archive, "provenance/source-validation.json", encode(value))


def test_selected_subset_still_requires_unselected_source_page_validation(tmp_path, orchestration, monkeypatch):
    source = miniature_source(tmp_path / "source", ("p", "q"))
    value = source_pass(source)
    value["checks"] = [check for check in value["checks"] if check["name"] != "page_files:q"]
    monkeypatch.setattr(bundle, "validate_dataset", lambda *args, **kwargs: value)
    with pytest.raises(ValueError, match="page_files:q"):
        bundle.export_bundle(source, tmp_path / "output", ["p"])
    assert not (tmp_path / "output").exists()


def test_code_change_during_projection_refused_before_write(tmp_path, orchestration, monkeypatch):
    source = miniature_source(tmp_path / "source")
    state = deepcopy(ENVIRONMENT)
    monkeypatch.setattr(bundle, "_projection_environment", lambda: deepcopy(state))

    def project(page, filename):
        state["projection_modules"]["exports_newseye.py"] = "f" * 64
        return manual_projection(page, filename)
    monkeypatch.setattr(bundle, "_project", project)
    with pytest.raises(ValueError, match="code/environment changed during preflight"):
        bundle.export_bundle(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_code_change_during_copy_preserves_partial_output(tmp_path, orchestration, monkeypatch):
    source = miniature_source(tmp_path / "source")
    state = deepcopy(ENVIRONMENT)
    original = bundle._source_snapshot
    calls = 0
    monkeypatch.setattr(bundle, "_projection_environment", lambda: deepcopy(state))

    def snapshot(root):
        nonlocal calls
        calls += 1
        if calls == 3:
            state["projection_modules"]["exports_newseye.py"] = "f" * 64
        return original(root)
    monkeypatch.setattr(bundle, "_source_snapshot", snapshot)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="code/environment changed; partial output preserved"):
        bundle.export_bundle(source, output)
    assert (output / "images/p.png").is_file()
    assert not (output / "manifest.json").exists()


def test_png_crc_is_insufficient_without_decodable_pixels(tmp_path):
    import struct
    import zlib

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", b"not-a-zlib-stream") + chunk(b"IEND", b""))
    image = tmp_path / "broken.png"
    image.write_bytes(data)
    page = {"image": {"width": 1, "height": 1, "color_mode": "L", "sha256": digest(data)}}
    with Image.open(image) as opened:
        opened.verify()  # Demonstrate why the additional decode is necessary.
    with pytest.raises(OSError, match="broken data stream"):
        bundle._png_errors(image, page)
