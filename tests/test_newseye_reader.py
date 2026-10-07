"""Reader-first tests: hand-authored XML/observations, never exporter output."""

from copy import deepcopy
import json
from pathlib import Path

from lxml import etree
import pytest

from mille_feuilles.newseye_reader import NewsEyeReadError, read_page

FIXTURES = Path(__file__).parent / "fixtures" / "newseye"
NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
Q = "{" + NS + "}"
ORDER = "fixture-1-order"
UNICODE = "fixture-2-unicode-hyphen-geometry"


def xml_bytes(name=ORDER, variant="expected"):
    return (FIXTURES / f"{name}.{variant}.xml").read_bytes()


def expected(name=ORDER, kind="reading"):
    data = json.loads((FIXTURES / f"{name}.expected-{kind}.json").read_text())
    return {key: value for key, value in data.items() if key not in {"format", "version", "note"}}


def tree(name=ORDER):
    return etree.fromstring(xml_bytes(name))


def by_id(root, identifier):
    return root.xpath("//*[@id=$identifier]", identifier=identifier)[0]


def ref(root, identifier):
    return root.xpath("//*[@regionRef=$identifier]", identifier=identifier)[0]


def observe(root):
    return read_page(etree.tostring(root))


def rejects(root, code=None):
    with pytest.raises(NewsEyeReadError) as caught:
        observe(root)
    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value.code, str) and caught.value.code
    assert isinstance(caught.value.details, dict)
    if code:
        assert caught.value.code == code
    return caught.value


@pytest.mark.parametrize(
    ("name", "variant"), [(ORDER, "expected"), (ORDER, "reader-variant"), (UNICODE, "expected")]
)
def test_frozen_independent_reading_and_every_geometry_point(name, variant):
    result = read_page(xml_bytes(name, variant))
    assert result["reading"] == expected(name)
    assert result["geometry"] == expected(name, "geometry")
    assert result["image"] == {"filename": "images/p.png", "width": 400, "height": 300}


def test_advert_stays_in_the_middle_and_ids_do_not_determine_order():
    reading = read_page(xml_bytes())["reading"]
    assert [region["id"] for region in reading["text_regions_in_order"]] == [
        "r_p_b0000",
        "r_p_b0004",
        "r_p_b0003",
        "r_p_b0001",
        "r_p_b0002",
    ]
    assert reading["advert_ranks"] == [2]


def test_swapping_only_reference_physical_order_does_not_change_reading():
    root = tree()
    group = root.find(f"{Q}Page/{Q}ReadingOrder/{Q}OrderedGroup")
    group[:] = list(reversed(group[:]))
    assert observe(root) == read_page(xml_bytes())


def test_word_parent_and_order_are_direct_observations():
    result = read_page(xml_bytes())
    assert result["word_ids_by_line"]["l_p_l00002"] == ["w_p_w000003", "w_p_w000004", "w_p_w000005"]
    assert result["word_ids_by_line"]["l_p_l00005"] == ["w_p_w000010", "w_p_w000011", "w_p_w000012"]


def test_moved_homographs_change_parent_observation_even_when_goldens_do_not():
    root = tree()
    first, second = by_id(root, "w_p_w000003"), by_id(root, "w_p_w000010")
    assert first.find(f"{Q}TextEquiv/{Q}Unicode").text == "Le"
    assert second.find(f"{Q}TextEquiv/{Q}Unicode").text == "Le"
    left, right = first.getparent(), second.getparent()
    left_index, right_index = left.index(first), right.index(second)
    left.remove(first)
    right.remove(second)
    left.insert(left_index, second)
    right.insert(right_index, first)
    mutated, original = observe(root), read_page(xml_bytes())
    assert mutated["reading"] == original["reading"]
    assert mutated["geometry"] == original["geometry"]
    assert mutated["word_ids_by_line"] != original["word_ids_by_line"]
    assert mutated["word_ids_by_line"]["l_p_l00002"][0] == "w_p_w000010"


def test_permuted_homographs_on_one_line_are_visible():
    root = tree()
    line = by_id(root, "l_p_l00002")
    words = line.findall(f"{Q}Word")
    for word in words:
        word.find(f"{Q}TextEquiv/{Q}Unicode").text = "Le"
    line.find(f"{Q}TextEquiv/{Q}Unicode").text = "Le Le Le"
    by_id(root, "r_p_b0002").find(f"{Q}TextEquiv/{Q}Unicode").text = "Le Le Le\nvoté."
    before = observe(root)
    first, second = words[:2]
    positions = line.index(first), line.index(second)
    line.remove(first)
    line.remove(second)
    line.insert(positions[0], second)
    line.insert(positions[1], first)
    after = observe(root)
    assert before["geometry"] == after["geometry"]
    assert before["reading"] == after["reading"]
    assert before["word_ids_by_line"] != after["word_ids_by_line"]


def test_exact_line_whitespace_and_unicode_are_preserved_without_hyphen_reconstruction():
    root = tree(UNICODE)
    line = by_id(root, "l_p_l00001")
    line.find(f"{Q}TextEquiv/{Q}Unicode").text = "La   disso-"
    region = by_id(root, "r_p_b0001")
    region.find(f"{Q}TextEquiv/{Q}Unicode").text = "La   disso-\nlution du conseil."
    result = observe(root)
    assert result["reading"]["text_regions_in_order"][1]["lines"][0][2] == "La   disso-"
    assert result["geometry"]["words"]["w_p_w000009"][0] == "disso-"
    assert result["geometry"]["lines"]["l_p_l00002"][1] == [[10, 82], [81, 82], [150, 82]]
    assert result["geometry"]["words"]["w_p_w000008"][1] == [[11, 50], [30, 50], [31, 66], [10, 66]]


@pytest.mark.parametrize(
    ("identifier", "custom"),
    [
        ("l_p_l00004", "readingOrder {index:0;}"),
        ("r_p_b0001", "readingOrder {index:3;} structure {}"),
        ("l_p_l00004", '{"readingOrder":0,"article":"p_a0002"}'),
        ("l_p_l00004", "readingOrder {index:0;} structure {id:p_a0002;evil; type:article;}"),
        ("l_p_l00004", "readingOrder {index:0;} structure {id:p_a0002; type:article; id:other;}"),
        (
            "l_p_l00004",
            "readingOrder {index:0;} structure {id:p_a0002; type:article;} structure {}",
        ),
        ("l_p_l00004", "readingOrder {index:0;} structure {type:article; id:p_a0002;}"),
        ("l_p_l00004", "readingOrder {index:-1;} structure {id:p_a0002; type:article;}"),
        ("l_p_l00004", "readingOrder {index:0.0;} structure {id:p_a0002; type:article;}"),
        ("l_p_l00004", "readingOrder {index:0;} structure {id:p_a0002; type:paragraph;}"),
        ("l_p_l00004", "readingOrder {index:0;}  structure {id:p_a0002; type:article;}"),
        ("l_p_l00004", "readingOrder {index:0;} structure {id:p_a0002; type:article; }"),
        ("r_p_b0001", "readingOrder {index:3;} structure {type:heading;} junk"),
    ],
)
def test_invalid_or_missing_custom_is_a_controlled_error(identifier, custom):
    root = tree()
    by_id(root, identifier).set("custom", custom)
    rejects(root, "custom")


def test_region_type_cannot_contradict_its_custom():
    root = tree()
    by_id(root, "r_p_b0001").set("type", "paragraph")
    rejects(root, "custom")


@pytest.mark.parametrize(("width", "kind", "ranks"), [(40, "texte", []), (51, "annonce", [2])])
def test_advert_threshold_is_inclusive(width, kind, ranks):
    root = tree()
    by_id(root, "a_p_b0003").find(f"{Q}Coords").set(
        "points", f"10,80 {10 + width},80 {10 + width},95 10,95"
    )
    reading = observe(root)["reading"]
    assert reading["advert_cover_max"]["r_p_b0003"] == pytest.approx(width / 102, abs=1e-12)
    assert reading["text_regions_in_order"][2]["kind"] == kind
    assert reading["advert_ranks"] == ranks


def test_coverage_uses_polygon_intersection_not_bounding_boxes():
    root = tree()
    by_id(root, "a_p_b0003").find(f"{Q}Coords").set("points", "10,80 112,80 10,95")
    reading = observe(root)["reading"]
    assert reading["advert_cover_max"]["r_p_b0003"] == 0.5
    assert reading["advert_ranks"] == [2]


def test_coverage_is_maximum_not_sum_or_union_and_does_not_depend_on_advert_id():
    root = tree()
    advert = by_id(root, "a_p_b0003")
    advert.set("id", "unrelated_identifier")
    advert.find(f"{Q}Coords").set("points", "10,80 40,80 40,95 10,95")
    second = deepcopy(advert)
    second.set("id", "another_advert")
    second.find(f"{Q}Coords").set("points", "82,80 112,80 112,95 82,95")
    root.find(f"{Q}Page").append(second)
    reading = observe(root)["reading"]
    assert reading["advert_cover_max"]["r_p_b0003"] == pytest.approx(30 / 102, abs=1e-12)
    assert reading["advert_ranks"] == []


@pytest.mark.parametrize("structure", ["heading", "caption"])
def test_advert_classification_precedes_text_structure(structure):
    root = tree()
    region = by_id(root, "r_p_b0003")
    region.set("type", structure)
    region.set("custom", f"readingOrder {{index:2;}} structure {{type:{structure};}}")
    assert observe(root)["reading"]["text_regions_in_order"][2]["kind"] == "annonce"


def test_caption_without_advert_reads_as_legende():
    root = tree()
    region = by_id(root, "r_p_b0001")
    region.set("type", "caption")
    region.set("custom", "readingOrder {index:3;} structure {type:caption;}")
    assert observe(root)["reading"]["text_regions_in_order"][3]["kind"] == "legende"


@pytest.mark.parametrize("swap_attribute", ["index", "regionRef"])
def test_reference_changes_with_unchanged_region_indices_are_contradictions(swap_attribute):
    root = tree()
    first, second = ref(root, "r_p_b0004"), ref(root, "r_p_b0003")
    before_order = [element.get("regionRef") for element in first.getparent()]
    a, b = first.get(swap_attribute), second.get(swap_attribute)
    first.set(swap_attribute, b)
    second.set(swap_attribute, a)
    if swap_attribute == "index":
        assert [element.get("regionRef") for element in first.getparent()] == before_order
    rejects(root, "reading_order")


def test_consistent_index_changes_move_the_advert_without_moving_xml_elements():
    root = tree()
    for identifier, index in [("r_p_b0004", 2), ("r_p_b0003", 1)]:
        ref(root, identifier).set("index", str(index))
        by_id(root, identifier).set(
            "custom", f"readingOrder {{index:{index};}} structure {{type:paragraph;}}"
        )
    reading = observe(root)["reading"]
    assert [r["id"] for r in reading["text_regions_in_order"]][:3] == [
        "r_p_b0000",
        "r_p_b0003",
        "r_p_b0004",
    ]
    assert reading["advert_ranks"] == [1]
    assert reading != expected()


@pytest.mark.parametrize("index", ["2", "5", "-1", "1.0", "NaN", "9" * 5000])
def test_duplicate_gap_or_invalid_reference_indices_fail(index):
    root = tree()
    ref(root, "r_p_b0004").set("index", index)
    rejects(root, "reading_order")


def test_missing_reference_reports_omissions_even_when_it_also_leaves_an_index_gap():
    root = tree()
    reference = ref(root, "r_p_b0004")
    reference.getparent().remove(reference)
    error = rejects(root, "omitted_text_regions")
    assert error.details["omitted_text_regions"] == ["r_p_b0004"]


@pytest.mark.parametrize("target", ["a_p_b0003", "s_p_b0005", "unknown", "r_p_b0000"])
def test_nontext_unknown_and_duplicate_targets_are_refused(target):
    root = tree()
    ref(root, "r_p_b0004").set("regionRef", target)
    rejects(root, "reference")


@pytest.mark.parametrize("index", [None, "0", "2"])
def test_line_index_is_required_unique_and_contiguous(index):
    root = tree()
    custom = "structure {id:p_a0001; type:article;}"
    if index is not None:
        custom = f"readingOrder {{index:{index};}} " + custom
    by_id(root, "l_p_l00003").set("custom", custom)
    rejects(root, "custom" if index is None else "reading_order")


def test_nested_advert_text_cannot_replace_top_level_text_region():
    root = tree()
    by_id(root, "a_p_b0003").append(by_id(root, "r_p_b0003"))
    rejects(root, "structure")


@pytest.mark.parametrize(
    "identifier", ["r_p_b0000", "l_p_l00000", "w_p_w000000", "mf_newseye_order"]
)
def test_ids_are_globally_unique_across_entity_kinds(identifier):
    root = tree()
    by_id(root, "w_p_w000012").set("id", identifier)
    rejects(root, "id")


@pytest.mark.parametrize("identifier", ["", "bad id", "bad;id", "bad/id", "é"])
def test_xml_ids_use_the_profile_grammar(identifier):
    root = tree()
    by_id(root, "w_p_w000012").set("id", identifier)
    rejects(root, "id")


@pytest.mark.parametrize(
    "points",
    [
        "10,10 200,30 200,10 10,30",
        "10,10 20,20 30,30",
        "10,10 10,10 10,10",
        "",
        "10,10 200,10 401,30 10,30",
        "-1,10 200,10 200,30 10,30",
        "10.5,10 200,10 200,30 10,30",
        "NaN,10 200,10 200,30 10,30",
        "10,10,10 200,10 200,30 10,30",
        "inf,10 200,10 200,30 10,30",
    ],
)
def test_unsafe_polygon_coordinates_are_controlled_errors(points):
    root = tree()
    by_id(root, "r_p_b0000").find(f"{Q}Coords").set("points", points)
    rejects(root, "geometry")


@pytest.mark.parametrize("points", ["10,26", "10,26 10,26", "10,26 401,26", "NaN,26 10,26"])
def test_baseline_requires_distinct_in_bounds_points(points):
    root = tree()
    by_id(root, "l_p_l00000").find(f"{Q}Baseline").set("points", points)
    rejects(root, "geometry")


def test_intermediate_baseline_point_is_not_discarded_or_simplified():
    root = tree(UNICODE)
    by_id(root, "l_p_l00002").find(f"{Q}Baseline").set("points", "10,82 81,83 150,82")
    result = observe(root)
    assert result["reading"] == expected(UNICODE)
    assert result["geometry"] != expected(UNICODE, "geometry")
    assert result["geometry"]["lines"]["l_p_l00002"][1] == [[10, 82], [81, 83], [150, 82]]


@pytest.mark.parametrize(
    ("identifier", "child"),
    [
        ("r_p_b0000", "Coords"),
        ("r_p_b0000", "TextEquiv"),
        ("l_p_l00000", "Baseline"),
        ("l_p_l00000", "Coords"),
        ("w_p_w000000", "Coords"),
        ("w_p_w000000", "TextEquiv"),
    ],
)
def test_required_geometry_and_text_structure_cannot_be_omitted(identifier, child):
    root = tree()
    node = by_id(root, identifier)
    node.remove(node.find(f"{Q}{child}"))
    rejects(root, "structure")


@pytest.mark.parametrize("identifier", ["r_p_b0000", "l_p_l00000", "w_p_w000000"])
def test_multiple_text_alternatives_are_not_silently_selected(identifier):
    root = tree()
    node = by_id(root, identifier)
    node.append(deepcopy(node.find(f"{Q}TextEquiv")))
    rejects(root, "structure")


@pytest.mark.parametrize(
    ("identifier", "text"),
    [
        ("w_p_w000000", "WRONG"),
        ("w_p_w000000", "two words"),
        ("l_p_l00000", "MILLE  WRONG"),
        ("r_p_b0000", "WRONG"),
        ("w_p_w000011", "marche\u0301"),
    ],
)
def test_contradictory_or_non_nfc_text_is_not_repaired(identifier, text):
    root = tree()
    by_id(root, identifier).find(f"{Q}TextEquiv/{Q}Unicode").text = text
    rejects(root, "text")


@pytest.mark.parametrize(
    "filename",
    [
        "/tmp/p.png",
        "../p.png",
        "images/../p.png",
        "images\\p.png",
        "https://host/p.png",
        "file:p.png",
        "",
        "./p.png",
        "images//p.png",
    ],
)
def test_image_filename_is_a_safe_relative_posix_reference(filename):
    root = tree()
    root.find(f"{Q}Page").set("imageFilename", filename)
    rejects(root, "image_path")


@pytest.mark.parametrize("dimension", ["0", "-1", "NaN", "10.5", str(2**53), "9" * 5000])
def test_dimensions_must_be_positive_safe_integers(dimension):
    root = tree()
    root.find(f"{Q}Page").set("imageWidth", dimension)
    rejects(root, "geometry")


@pytest.mark.parametrize(
    "xml", [b"", b"<broken>", b"<PcGts/>", b"<r xmlns='urn:other'/>", "not bytes", None]
)
def test_malformed_namespace_and_input_type_are_controlled_errors(xml):
    with pytest.raises(NewsEyeReadError):
        read_page(xml)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
@pytest.mark.parametrize(
    "declaration",
    [
        '<!DOCTYPE PcGts [<!ENTITY text "MILLE">]>',
        '<!DOCTYPE PcGts SYSTEM "http://127.0.0.1:1/forbidden.dtd">',
        '<!DOCTYPE PcGts [<!ENTITY text SYSTEM "file:///nonexistent-reader-security-sentinel">]>',
    ],
)
def test_dtds_entities_and_external_resources_are_refused_including_utf16(encoding, declaration):
    xml = xml_bytes().decode().split("?>", 1)[1]
    document = f'<?xml version="1.0" encoding="{encoding}"?>{declaration}{xml}'
    with pytest.raises(NewsEyeReadError) as caught:
        read_page(document.encode(encoding))
    assert caught.value.code in {"dtd", "xml", "xml_external_resource"}


def test_general_entity_is_never_expanded_into_observed_text():
    xml = xml_bytes().decode().split("?>", 1)[1].replace("MILLE", "&injected;")
    document = '<!DOCTYPE PcGts [<!ENTITY injected "MILLE">]>' + xml
    with pytest.raises(NewsEyeReadError) as caught:
        read_page(document.encode())
    assert caught.value.code == "dtd"


def test_document_namespace_cannot_be_spoofed_by_local_names():
    xml = xml_bytes().replace(NS.encode(), b"urn:wrong-namespace")
    with pytest.raises(NewsEyeReadError) as caught:
        read_page(xml)
    assert caught.value.code == "structure"


def test_reading_reference_cannot_hide_character_content_in_an_empty_element():
    root = tree()
    ref(root, "r_p_b0000").text = "not permitted by the profile"
    rejects(root, "structure")


def test_complete_local_profile_requires_word_observations_on_every_line():
    root = tree()
    line = by_id(root, "l_p_l00000")
    for word in line.findall(f"{Q}Word"):
        line.remove(word)
    rejects(root, "text")


def test_nontext_region_type_is_observed_even_without_advert_coverage():
    root = tree()
    page = root.find(f"{Q}Page")
    graphic = etree.SubElement(page, f"{Q}GraphicRegion", id="independent_graphic")
    etree.SubElement(graphic, f"{Q}Coords", points="350,250 380,250 380,280 350,280")
    before = observe(root)
    graphic.tag = f"{Q}AdvertRegion"
    after = observe(root)
    for unchanged in ("reading", "geometry", "word_ids_by_line", "image"):
        assert before[unchanged] == after[unchanged]
    assert before["region_types"]["independent_graphic"] == "GraphicRegion"
    assert after["region_types"]["independent_graphic"] == "AdvertRegion"
