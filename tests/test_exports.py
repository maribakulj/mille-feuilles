"""Independent composition fixtures: no renderer or canonical schema helpers."""
import copy
import json
import pytest
from lxml import etree as ET

from mille_feuilles.exports import ALTO_NS, PAGE_NS, export_coco, export_page, validate_exports


def box(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


@pytest.fixture
def page():
    # The continuation is physically ABOVE the preceding block on purpose.
    block_specs = [
        ("head", "titre", "news", 2, ["title1", "title2"]),
        ("bottom", "texte", "news", 140, ["split1"]),
        ("top", "legende", "news", 50, ["split2"]),
        ("advert", "annonce", "ad", 80, ["adline"]),
        ("table", "tableau", "tablearticle", 110, ["tableline"]),
        ("other", "autre", "misc", 180, ["otherline"]),
        ("picture", "illustration", None, 220, []),
        ("rule", "separateur", None, 240, []),
    ]
    blocks = [{"id": bid, "category": category, "article_id": article, "polygon": box(5.5, y + 0.5, 200, 34 if bid == "head" else 25), "line_ids": lids} for bid, category, article, y, lids in block_specs]
    # Triangle, so COCO polygon area cannot be accidentally its bbox area.
    blocks[-2]["polygon"] = [[10.5, 220.5], [60.5, 220.5], [35.5, 240.5]]
    blocks[-1]["polygon"] = box(5.5, 260.5, 200, 1)
    texts = {"title1": "Échos  de ſociété", "title2": "La ﬁne œuvre", "split1": "Inter-", "split2": "national café.", "adline": "À vendre", "tableline": "Prix 12", "otherline": "Fin."}
    lines, words = [], []
    for block in blocks:
        for rank, lid in enumerate(block["line_ids"]):
            y = block["polygon"][0][1] + 2 + 15 * rank
            text = texts[lid]
            line = {"id": lid, "block_id": block["id"], "polygon": box(7.5, y, 190, 13), "baseline": [[7.5, y + 10], [197.5, y + 10]], "text": text, "word_ids": [], "legibility": "readable"}
            offset = 0
            for index, token in enumerate(text.split()):
                start = text.index(token, offset)
                end = start + len(token)
                wid = f"{lid}_word{index}"
                line["word_ids"].append(wid)
                hyp = None
                if lid == "split1" or (lid == "split2" and index == 0):
                    hyp = {"group_id": "across_blocks", "part": "start" if lid == "split1" else "end", "reconstructed_text": "International"}
                words.append({"id": wid, "line_id": lid, "polygon": box(7.5 + start * 5, y, len(token) * 5, 13), "text": token, "char_span": [start, end], "legibility": "readable", "hyphenation": hyp})
                offset = end
            lines.append(line)
    # Storage arrays deliberately disagree with logical order.
    return {"schema_version": "0.2.0", "page_id": "fixture", "language": "fr", "image": {"path": "images/fixture.png", "width": 220, "height": 300},
            "articles": [{"id": "news", "block_ids": ["head", "bottom", "top"]}, {"id": "ad", "block_ids": ["advert"]}, {"id": "tablearticle", "block_ids": ["table"]}, {"id": "misc", "block_ids": ["other"]}],
            "blocks": list(reversed(blocks)), "lines": list(reversed(lines)), "words": list(reversed(words)),
            "reading_order": {"block_ids": ["head", "bottom", "top", "advert", "table", "other"], "unordered_block_ids": ["picture", "rule"], "line_ids": ["title1", "title2", "split1", "split2", "adline", "tableline", "otherline"]}}


def export_all(page, root):
    paths = export_page(page, root)
    export_coco([page], root)
    return paths


def test_official_schemas_and_roundtrip(page, tmp_path):
    paths = export_all(page, tmp_path)
    assert validate_exports(tmp_path, [page]) == []
    assert paths == {"page": "exports/page/fixture.xml", "alto": "exports/alto/fixture.xml", "report": "exports/reports/fixture.json"}
    xml = ET.parse(str(tmp_path / paths["page"]))
    ns = {"p": PAGE_NS}
    assert xml.xpath("//p:TextLine/@id", namespaces=ns) == ["l_" + lid for lid in page["reading_order"]["line_ids"]]
    assert xml.xpath("//p:TextLine[@id='l_title1']/p:TextEquiv/p:Unicode/text()", namespaces=ns) == ["Échos  de ſociété"]
    assert xml.xpath("//p:AdvertRegion/p:TextRegion/p:TextLine/@id", namespaces=ns) == ["l_adline"]
    assert xml.xpath("//p:TableRegion/p:TextRegion/p:TextLine/@id", namespaces=ns) == ["l_tableline"]
    assert xml.xpath("//p:ReadingOrder//p:RegionRef/@regionRef", namespaces=ns) == ["b_picture", "b_rule"]
    # Exact half rounds toward +infinity, not Python's banker's rounding.
    assert xml.xpath("//p:TextRegion[@id='b_head']/p:Coords/@points", namespaces=ns) == ["6,3 206,3 206,37 6,37"]
    alto = ET.parse(str(tmp_path / paths["alto"]))
    assert alto.xpath("//a:String[@SUBS_TYPE]/@CONTENT", namespaces={"a": ALTO_NS}) == ["Inter-", "national"]
    assert alto.xpath("//a:String[@SUBS_TYPE]/@SUBS_CONTENT", namespaces={"a": ALTO_NS}) == ["International", "International"]
    report = json.loads((tmp_path / paths["report"]).read_text())
    assert report["page_container_mapping"] == {"c_advert": "advert", "c_table": "table"}
    assert report["id_mapping"]["w_split1_word0"] == "split1_word0"


def test_exports_are_byte_reproducible(page, tmp_path):
    export_all(page, tmp_path / "first")
    export_all(page, tmp_path / "second")
    first = {p.relative_to(tmp_path / "first"): p.read_bytes() for p in (tmp_path / "first").rglob("*") if p.is_file()}
    second = {p.relative_to(tmp_path / "second"): p.read_bytes() for p in (tmp_path / "second").rglob("*") if p.is_file()}
    assert first == second


@pytest.mark.parametrize("kind,xpath,attribute,new_value", [
    ("page", ".//p:TextLine[@id='l_title1']/p:TextEquiv/p:Unicode", None, "Echos de societe"),
    ("page", ".//p:RegionRefIndexed[@index='0']", "regionRef", "b_bottom"),
    ("page", ".//p:Word[@id='w_split1_word0']/p:Coords", "points", "30,140 60,140 60,153 30,153"),
    ("page", ".//p:TextRegion[@id='b_head']", "custom", '{"category":"texte","article_id":"news"}'),
    ("page", ".//p:TextRegion[@id='b_head']", "custom", '{"category":"titre","article_id":"ad"}'),
    ("page", ".//p:Page", "primaryLanguage", "English"),
    ("page", ".//p:TextRegion[@id='c_advert']", "id", "c_not_the_advert"),
    ("alto", ".//a:String[@ID='w_title1_word0']", "CONTENT", "Echos"),
    ("alto", ".//a:ElementRef[@REF='b_head']", "REF", "b_bottom"),
    ("alto", ".//a:TextLine[@ID='l_title1']", "BASELINE", "7.5,20 197.5,20"),
    ("alto", ".//a:TextBlock[@ID='b_head']", "TAGREFS", "category_texte a_news"),
    ("alto", ".//a:String[@ID='w_split1_word0']", "SUBS_TYPE", "HypPart2"),
    ("alto", ".//a:OtherTag[@ID='s_title1']", "DESCRIPTION", "[1,1]"),
    ("alto", ".//a:TextLine[@ID='l_title1']", "BASELINE", "NaN,20 197.5,20"),
    ("alto", ".//a:TextBlock[@ID='b_head']", "WIDTH", "NaN"),
    ("alto", ".//a:Page", "LANG", "en"),
])
def test_detects_valid_xml_semantic_corruption(page, tmp_path, kind, xpath, attribute, new_value):
    paths = export_all(page, tmp_path)
    path = tmp_path / paths[kind]
    xml = ET.parse(str(path))
    target = xml.find(xpath, {"p": PAGE_NS, "a": ALTO_NS})
    if attribute:
        target.set(attribute, new_value)
    else:
        target.text = new_value
    xml.write(str(path), encoding="UTF-8", xml_declaration=True)
    errors = validate_exports(tmp_path, [page])
    assert errors and any(kind in error for error in errors)


def test_xsd_failure_is_reported(page, tmp_path):
    paths = export_all(page, tmp_path)
    path = tmp_path / paths["page"]
    xml = ET.parse(str(path))
    xml.find(f"{{{PAGE_NS}}}Page").set("notInSchema", "invalid")
    xml.write(str(path))
    assert any("notInSchema" in error for error in validate_exports(tmp_path, [page]))


def test_coco_area_ids_and_multiple_pages(page, tmp_path):
    second = copy.deepcopy(page)
    second["page_id"] = "another"
    second["image"]["path"] = "images/another.png"
    for p in (page, second):
        export_page(p, tmp_path)
    output = export_coco([page, second], tmp_path)
    assert validate_exports(tmp_path, [page, second]) == []
    coco = json.loads(output.read_text())
    assert [c["name"] for c in coco["categories"]] == ["titre", "texte", "legende", "annonce", "tableau", "illustration", "separateur", "autre"]
    illustrations = [a for a in coco["annotations"] if a["category_id"] == 6]
    assert len(illustrations) == 2
    assert all(a["area"] == 500 and a["bbox"] == [10.5, 220.5, 50, 20] for a in illustrations)
    assert len({a["id"] for a in coco["annotations"]}) == 16
    illustrations[0]["area"] = 1000
    output.write_text(json.dumps(coco))
    assert any(".area differs" in e for e in validate_exports(tmp_path, [page, second]))


def test_coco_refuses_duplicate_page_ids(page, tmp_path):
    with pytest.raises(ValueError, match="Duplicate page_id"):
        export_coco([page, page], tmp_path)


def test_rounded_degenerate_polygon_is_rejected(page, tmp_path):
    next(b for b in page["blocks"] if b["id"] == "rule")["polygon"] = box(10.1, 270.1, 100, 0.1)
    with pytest.raises(ValueError, match="degenerates"):
        export_page(page, tmp_path)


def test_nonreadable_is_preserved_without_fake_ocr_confidence(page, tmp_path):
    page["words"][0]["legibility"] = "uncertain"
    lid = page["words"][0]["line_id"]
    next(line for line in page["lines"] if line["id"] == lid)["legibility"] = "uncertain"
    paths = export_all(page, tmp_path)
    assert validate_exports(tmp_path, [page]) == []
    alto = ET.parse(str(tmp_path / paths["alto"]))
    assert not alto.xpath("//@WC | //@CC")


def test_missing_files_return_errors(page, tmp_path):
    errors = validate_exports(tmp_path, [page])
    assert len(errors) == 4  # sidecar, PAGE, ALTO and COCO


def test_symlink_escape_is_rejected(page, tmp_path):
    lot, elsewhere = tmp_path / "lot", tmp_path / "elsewhere"
    lot.mkdir()
    elsewhere.mkdir()
    (lot / "exports").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError):
        export_page(page, lot)
    assert not list(elsewhere.iterdir())
    assert validate_exports(lot, [page])


def test_page_identifier_cannot_escape_output_root(page, tmp_path):
    page["page_id"] = "../../escape"
    with pytest.raises(ValueError, match="identifier"):
        export_page(page, tmp_path)
    assert validate_exports(tmp_path, [page])


@pytest.mark.parametrize("field,replacement", [
    ("page_container_mapping", {"c_advert": "wrong_block"}),
    ("id_mapping", {}),
    ("articles", []),
    ("not_represented", None),
    ("not_represented", {"page": [], "alto": [], "coco": []}),
    ("custom_metadata", {}),
    ("paths", {"page": "exports/page/other.xml"}),
    ("canonical_path", "pages/other.json"),
    ("schema_version", "0.1.0"),
    ("schemas", {}),
    ("notes", []),
])
def test_sidecar_semantics_are_checked_independently_of_manifest_hashes(page, tmp_path, field, replacement):
    paths = export_all(page, tmp_path)
    path = tmp_path / paths["report"]
    report = json.loads(path.read_text())
    if replacement is None:
        report.pop(field)
    else:
        report[field] = replacement
    path.write_text(json.dumps(report))
    # This layer has no manifest digest to rely on: changing a digest in a
    # dataset cannot bypass these semantic report checks.
    errors = validate_exports(tmp_path, [page])
    assert any(f"export report {field}" in error for error in errors)


def test_sidecar_requires_a_json_object(page, tmp_path):
    paths = export_all(page, tmp_path)
    (tmp_path / paths["report"]).write_text("[]")
    assert any("export report must be a JSON object" in error for error in validate_exports(tmp_path, [page]))
