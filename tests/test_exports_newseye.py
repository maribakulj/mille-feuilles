"""Producer tests for the page-newseye-v1 profile, judged by independent evidence only.

Evidence: hand-written golden XML, readings and geometry (tests/fixtures/newseye, pinned before the
producer existed), the independent reader (newseye_reader, frozen before this file), the archived
PAGE 2019 XSD and the report schema. Expected values are never derived from the producer.
"""

import json
import math
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from lxml import etree as ET

from mille_feuilles.exports import _parser, _schema
from mille_feuilles.exports_newseye import NewsEyeExportError, project_page
from mille_feuilles.newseye_reader import read_page

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/newseye"
GOLDEN = ("fixture-1-order", "fixture-2-unicode-hyphen-geometry")
DESCRIPTIVE = ("format", "version", "note")


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def c14n(data: bytes) -> bytes:
    return ET.tostring(ET.fromstring(data, ET.XMLParser(remove_blank_text=True)), method="c14n2")


def observed(name):
    return {k: v for k, v in load(name).items() if k not in DESCRIPTIVE}


# --- fixtures: golden XML, XSD, independent reading -----------------------------------


@pytest.mark.parametrize("name", GOLDEN)
def test_output_equals_the_hand_written_golden_xml(name):
    xml, _ = project_page(load(f"{name}.json"))
    assert c14n(xml) == c14n((FIXTURES / f"{name}.expected.xml").read_bytes())
    assert xml.startswith(b"<?xml version='1.0' encoding='UTF-8'?>")


@pytest.mark.parametrize("name", GOLDEN)
def test_output_is_valid_page_2019(name):
    xml, _ = project_page(load(f"{name}.json"))
    assert _schema("page").validate(ET.fromstring(xml, _parser()))


@pytest.mark.parametrize("name", GOLDEN)
def test_independent_reader_observes_expected_reading_and_every_point(name):
    xml, _ = project_page(load(f"{name}.json"))
    result = read_page(xml)
    assert result["reading"] == observed(f"{name}.expected-reading.json")
    assert result["geometry"] == observed(f"{name}.expected-geometry.json")


@pytest.mark.parametrize("name", GOLDEN)
def test_region_types_and_word_attachment_follow_the_canonical_page(name):
    page = load(f"{name}.json")
    result = read_page(project_page(page)[0])
    categories = {b["id"]: b["category"] for b in page["blocks"]}
    expected = {}
    for bid in page["reading_order"]["block_ids"]:
        expected[f"r_{bid}"] = "TextRegion"
        if categories[bid] == "annonce":
            expected[f"a_{bid}"] = "AdvertRegion"
    for bid in page["reading_order"]["unordered_block_ids"]:
        expected[{"separateur": "s_", "illustration": "g_"}[categories[bid]] + bid] = (
            "SeparatorRegion" if categories[bid] == "separateur" else "GraphicRegion")
    assert result["region_types"] == expected
    assert result["word_ids_by_line"] == {
        f"l_{line['id']}": [f"w_{wid}" for wid in line["word_ids"]] for line in page["lines"]
    }
    assert all(words for words in result["word_ids_by_line"].values())  # >= 1 Word per line


def test_three_point_baseline_and_rounding_are_projected_point_by_point():
    xml, _ = project_page(load("fixture-2-unicode-hyphen-geometry.json"))
    lines = read_page(xml)["geometry"]["lines"]
    assert lines["l_p_l00002"][1] == [[10, 82], [81, 82], [150, 82]]
    assert read_page(xml)["geometry"]["words"]["w_p_w000008"][1] == [[11, 50], [30, 50], [31, 66], [10, 66]]


# --- refusals: controlled, before any output ------------------------------------------


@pytest.mark.parametrize("name", ["fixture-3-free-block", "fixture-4-advert-overlap"])
def test_expected_refusals_of_the_profile(name):
    expected = load(f"{name}.expected-error.json")
    with pytest.raises(NewsEyeExportError) as caught:
        project_page(load(f"{name}.json"))
    assert caught.value.code == expected["code"]
    assert isinstance(caught.value, ValueError)
    for block_id in expected["block_ids"]:
        assert block_id in str(caught.value)


def mutated(mutate, name="fixture-1-order.json"):
    page = load(name)
    mutate(page)
    return page


def _block(page, bid):
    return next(b for b in page["blocks"] if b["id"] == bid)


@pytest.mark.parametrize(
    "mutate, code",
    [
        (lambda p: p.update(language="de"), "language"),
        (lambda p: _block(p, "p_b0002").update(category="tableau"), "table_block"),
        (lambda p: _block(p, "p_b0002").update(category="inconnue"), "category"),
        (lambda p: _block(p, "p_b0002").update(article_id="p_a;0001"), "custom_value"),
        (lambda p: _block(p, "p_b0002").update(article_id=None), "free_text_block"),
        (lambda p: p["words"][0].update(id="p w000000"), "custom_value"),
        (lambda p: p["reading_order"]["block_ids"].remove("p_b0004"), "reading_order"),
        (lambda p: p["reading_order"]["block_ids"].append("p_b0005"), "reading_order"),
        (lambda p: p["reading_order"]["unordered_block_ids"].append("p_b0001"), "reading_order"),
        (lambda p: p["reading_order"]["block_ids"].append("p_b0000"), "reading_order"),
        (lambda p: next(line for line in p["lines"] if line["id"] == "p_l00003").update(word_ids=[]), "empty_line"),
        (lambda p: p["words"][6].update(polygon=[[210, 100], [210.2, 100], [210.4, 100.1], [210, 100.2]]), "geometry"),
        (lambda p: next(line for line in p["lines"] if line["id"] == "p_l00003").update(
            baseline=[[210.2, 112], [210.4, 112]]), "geometry"),
    ],
)
def test_controlled_refusals_raise_before_output(mutate, code):
    with pytest.raises(NewsEyeExportError) as caught:
        project_page(mutated(mutate))
    assert caught.value.code == code


@pytest.mark.parametrize(
    "value", ["/abs/p.png", "../p.png", "images/../p.png", "images\\p.png", "file:images/p.png",
              "http://x/p.png", "", "images//p.png", "./p.png", 3, 3.5,
              "images/a:b.png", "C:images/p.png", "images/a\tb.png", "images/a\nb.png", "images/a\x7fb.png",
              "images/a\x00b.png", "images/a\x1fb.png", "images/p.png/", "images/./p.png"],
)
def test_unsafe_image_filename_is_refused(value):
    with pytest.raises(NewsEyeExportError) as caught:
        project_page(load("fixture-1-order.json"), image_filename=value)
    assert caught.value.code == "image_filename"


@pytest.mark.parametrize("value", ["images/a\x80b.png", "images/é t.png", "images/p-1.2_x.png"])
def test_image_filename_rule_matches_the_reader(value):
    # Characters outside U+0000..U+001F, U+007F and ":" are accepted by both sides alike.
    xml, report = project_page(load("fixture-1-order.json"), image_filename=value)
    assert read_page(xml)["image"]["filename"] == value == report["image_filename"]


def test_image_filename_override_is_written_and_reported():
    xml, report = project_page(load("fixture-1-order.json"), image_filename="images/mf_0001.png")
    assert read_page(xml)["image"]["filename"] == "images/mf_0001.png"
    assert report["image_filename"] == "images/mf_0001.png"


# --- report: schema constants and independent cross-checks ----------------------------


@pytest.mark.parametrize("name", GOLDEN)
def test_report_matches_schema_and_cross_checks(name):
    page = load(f"{name}.json")
    xml, report = project_page(page)
    schema = json.loads((ROOT / "schemas/newseye-report.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(report)) == []
    assert report["page_id"] == page["page_id"]
    assert report["image_filename"] == read_page(xml)["image"]["filename"]
    xml_ids = {e.get("id") for e in ET.fromstring(xml).iter() if e.get("id")} - {"mf_newseye_order"}
    assert set(report["id_mapping"]) == xml_ids
    assert list(report["id_mapping"]) == sorted(report["id_mapping"])
    nature = {**{b["id"]: "block" for b in page["blocks"]}, **{line["id"]: "line" for line in page["lines"]},
              **{w["id"]: "word" for w in page["words"]}}
    prefix = {"r": "block", "a": "block", "s": "block", "g": "block", "l": "line", "w": "word"}
    for xml_id, canonical in report["id_mapping"].items():
        assert nature[canonical] == prefix[xml_id.split("_", 1)[0]]
        assert xml_id.split("_", 1)[1] == canonical


def test_report_version_and_constants_follow_the_report_schema():
    from mille_feuilles import exports_newseye

    schema = json.loads((ROOT / "schemas/newseye-report.schema.json").read_text(encoding="utf-8"))
    properties = schema["properties"]
    _, report = project_page(load("fixture-1-order.json"))
    assert exports_newseye.REPORT_VERSION == properties["version"]["const"] == report["version"] == "2"
    assert report["not_represented"] == properties["not_represented"]["const"]
    assert report["notes"] == properties["notes"]["const"]
    assert len(report["not_represented"]) == len(set(report["not_represented"])) == 25


def test_projection_is_pure_and_deterministic():
    page = load("fixture-2-unicode-hyphen-geometry.json")
    before = deepcopy(page)
    first, second = project_page(page), project_page(page)
    assert first[0] == second[0] and first[1] == second[1]
    assert page == before


# --- real canonical pages (local lots; not versioned) ---------------------------------


def _round_like_spec(points, width, height):
    """§ 5, written here independently: floor(v + 0.5), clamped to the image."""
    return [[min(width, max(0, math.floor(x + 0.5))), min(height, max(0, math.floor(y + 0.5)))]
            for x, y in points]


REAL_PAGES = [
    ROOT / "runs/pilot-v0.2-r2/pages/mf_0003.json",
    ROOT / "runs/accept-layout-v2/lots/compact-identity-x1/pages/mf_0001.json",
    ROOT / "runs/accept-layout-v2/lots/compact-identity-x1/pages/mf_0000.json",
]


@pytest.mark.parametrize("path", REAL_PAGES, ids=lambda p: "/".join(p.parts[-4:]))
def test_real_page_reading_equals_the_canonical_page(path):
    if not path.is_file():
        pytest.skip(f"local lot absent (runs/ is not versioned): {path}")
    page = json.loads(path.read_text(encoding="utf-8"))
    xml, _ = project_page(page, image_filename=f"images/{page['page_id']}.png")
    result = read_page(xml)
    width, height = page["image"]["width"], page["image"]["height"]
    blocks = {b["id"]: b for b in page["blocks"]}
    order = page["reading_order"]["block_ids"]
    kinds = {"titre": "titre", "texte": "texte", "annonce": "annonce", "legende": "legende", "autre": "texte"}
    regions = result["reading"]["text_regions_in_order"]
    assert [r["id"] for r in regions] == [f"r_{bid}" for bid in order]
    assert [r["kind"] for r in regions] == [kinds[blocks[bid]["category"]] for bid in order]
    assert result["reading"]["advert_ranks"] == [i for i, bid in enumerate(order) if blocks[bid]["category"] == "annonce"]
    assert result["reading"]["omitted_text_regions"] == []
    line_articles = {line_id: article for r in regions for line_id, article, _ in r["lines"]}
    lines = {line["id"]: line for line in page["lines"]}
    assert line_articles == {f"l_{lid}": blocks[lines[lid]["block_id"]]["article_id"] for lid in lines}
    texts = {line_id: text for r in regions for line_id, _, text in r["lines"]}
    assert texts == {f"l_{lid}": lines[lid]["text"] for lid in lines}
    geometry = result["geometry"]
    for word in page["words"]:
        assert geometry["words"][f"w_{word['id']}"] == [word["text"], _round_like_spec(word["polygon"], width, height)]
    for line in page["lines"]:
        assert geometry["lines"][f"l_{line['id']}"] == [
            _round_like_spec(line["polygon"], width, height), _round_like_spec(line["baseline"], width, height)]
    for bid in order:
        assert geometry["regions"][f"r_{bid}"] == _round_like_spec(blocks[bid]["polygon"], width, height)
    if path.name == "mf_0003.json" and "pilot-v0.2-r2" in str(path):
        assert sum(r["kind"] == "titre" for r in regions) == 26
        assert len(line_articles) == 535
        assert result["reading"]["advert_ranks"][:4] == [3, 4, 24, 32]
        assert len(result["reading"]["advert_ranks"]) == 14
