"""Consecutive bodies: canonical JSON and original text only, without raster output."""

from copy import deepcopy
import hashlib
import json

from jsonschema import Draft202012Validator
import pytest

from mille_feuilles import validation as v
from test_layout_validation import fixture_page, rect


BODY = "Été Été  \n\n\nÉté Été\n\nMot\n\nMot"
FIRST_END = len("Été Été  \n\n\nÉté Été")
LAST_START = len("Été Été  \n\n\nÉté Été\n\n")


def sequence(page, aid="story"):
    return next(a for a in page["articles"] if a["id"] == aid)["extensions"]["mf:source_sequence"]


def body_span(page, aid="story"):
    return next(s for s in page["provenance"]["text_spans"]
                if s["article_id"] == aid and s["asset_id"] == "text_body")


@pytest.fixture
def active():
    page = fixture_page()
    page["provenance"]["parameters"]["content_profile"] = "consecutive-v1"
    for line in page["lines"]:
        if line["block_id"] in ("body", "body_second"):
            line["text"] = "Été"
    for word in page["words"]:
        if word["line_id"].startswith("body"):
            word["text"] = "Été"
    # The lower body contains two identical source units, retained with multiplicity.
    line = next(line for line in page["lines"] if line["block_id"] == "lower_block")
    word = next(word for word in page["words"] if word["id"] == line["word_ids"][0])
    other = deepcopy(word)
    x0, y0 = word["polygon"][0]
    x1, y1 = word["polygon"][2]
    middle = (x0 + x1) / 2
    word["polygon"] = rect([x0, y0, middle - 2, y1])
    other.update(id="lower_second_word", char_span=[4, 7], polygon=rect([middle + 2, y0, x1, y1]))
    page["words"].append(other)
    line["word_ids"].append(other["id"])
    line["text"] = "Mot Mot"
    spans = page["provenance"]["text_spans"]
    spans[:] = [s for s in spans if s["block_ids"] != ["body_second"]]
    body_span(page).update(start=0, end=FIRST_END, block_ids=["body", "body_second"])
    body_span(page, "lower_story").update(start=LAST_START, end=len(BODY))
    for aid, start, end, interval in [
        ("story", 0, FIRST_END, [0, 2]), ("lower_story", LAST_START, len(BODY), [2, 4]),
    ]:
        article = next(a for a in page["articles"] if a["id"] == aid)
        article["extensions"]["mf:source_sequence"] = {
            "version": "1", "asset_id": "text_body", "start": start, "end": end, "unit_range": interval,
        }
    texts = {"text_body": BODY, "text_title": "Mot", "text_ad": "Mot",
             "text_short": "Seul.", "text_second": "Un autre\n\nDocument."}
    roles = {"text_body": "body", "text_short": "body", "text_second": "body",
             "text_title": "title", "text_ad": "advertisement"}
    assets = {key: {"id": key, "kind": "text", "sha256": hashlib.sha256(raw.encode()).hexdigest(),
                    "metadata": {"role": roles[key], "source_document_id": f"doc_{key}"}}
              for key, raw in texts.items()}
    for span in spans:
        span["source_document_id"] = assets[span["asset_id"]]["metadata"]["source_document_id"]
    return page, assets, texts


@pytest.fixture
def context(tmp_path, active):
    _, assets, texts = active
    config = {"render": {"content_profile": "consecutive-v1", "layout_profile": v.LAYOUT_PROFILE,
                         "degradation_profile": {"profile": "identity"}}}
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    documents = [
        {"asset_id": aid, "source_document_id": f"doc_{aid}", "sha256": assets[aid]["sha256"],
         "unit_count": count, "eligible": count >= 2,
         "reason": None if count >= 2 else "fewer_than_two_body_units"}
        for aid, count in [("text_body", 4), ("text_second", 2), ("text_short", 1)]
    ]
    receipt = {"version": "1", "profile": "consecutive-v1", "calibrated": False, "documents": documents}
    manifest = {"profile": v.LAYOUT_PROFILE, "config": {"path": "config.json"},
                "extensions": {"mf:content_profile": receipt}}
    return tmp_path, manifest, assets, texts


def test_complete_multiblock_body_and_duplicate_units_pass(active, context):
    page, assets, texts = active
    assert v.validate_page(page) == []
    assert v.validate_text_provenance(page, texts) == []
    assert v._content_source_errors(page, assets, texts) == []
    assert v._load_content_profile(*context) == ("consecutive-v1", [])


def replace_body_source(active, first_part, interval):
    page, assets, texts = active
    raw = first_part + "\n\nMot\n\nMot"
    texts["text_body"] = raw
    assets["text_body"]["sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    sequence(page).update(end=len(first_part), unit_range=interval)
    body_span(page)["end"] = len(first_part)
    sequence(page, "lower_story").update(start=len(first_part) + 2, end=len(raw),
                                        unit_range=[interval[1], interval[1] + 2])
    body_span(page, "lower_story").update(start=len(first_part) + 2, end=len(raw))


def test_three_units_are_accepted_without_changing_composed_words(active):
    page, assets, texts = active
    replace_body_source(active, "Été\n\nÉté\n\nÉté Été", [0, 3])
    assert v.validate_page(page) == []
    assert v.validate_text_provenance(page, texts) == []
    assert v._content_source_errors(page, assets, texts) == []


def test_one_span_keeps_hyphenation_across_body_columns(active):
    page, assets, texts = active
    replace_body_source(active, "Été dissolution\n\nÉté", [0, 2])
    blocks = {b["id"]: b for b in page["blocks"]}
    lines = {line["id"]: line for line in page["lines"]}
    words = {word["id"]: word for word in page["words"]}
    endpoints = [(blocks["body"]["line_ids"][-1], "disso-", "start"),
                 (blocks["body_second"]["line_ids"][0], "lution", "end")]
    for lid, text, part in endpoints:
        line = lines[lid]
        line["text"] = text
        words[line["word_ids"][0]].update(text=text, char_span=[0, len(text)], hyphenation={
            "group_id": "hyp_columns", "part": part, "reconstructed_text": "dissolution",
        })
    assert v.validate_page(page) == []
    assert v.validate_text_provenance(page, texts) == []
    assert v._content_source_errors(page, assets, texts) == []


@pytest.mark.parametrize("interval", [[0, 1], [0, 4], [2, 0], [0, 0]])
def test_implicit_unit_count_is_two_or_three(active, interval):
    page, _, _ = active
    sequence(page)["unit_range"] = interval
    assert any("two or three" in e for e in v.validate_page(page))


@pytest.mark.parametrize("interval", [[1, 3], [3, 5], [9, 11]])
def test_wrong_or_out_of_document_window_fails(active, interval):
    page, assets, texts = active
    sequence(page)["unit_range"] = interval
    assert v.validate_page(page) == []  # Count alone looks valid.
    assert v.validate_text_provenance(page, texts) == []  # Source slice still matches every word.
    assert v._content_source_errors(page, assets, texts)


def test_whitespace_equivalent_slice_still_needs_exact_unit_boundary(active):
    page, assets, texts = active
    sequence(page)["end"] += 1  # Include one source separator: tokens are unchanged.
    body_span(page)["end"] += 1
    assert v.validate_page(page) == []
    assert v.validate_text_provenance(page, texts) == []
    assert any("exact consecutive unit boundaries" in e for e in v._content_source_errors(page, assets, texts))


def test_missing_duplicate_unit_cannot_be_hidden_by_another_occurrence(active):
    page, _, texts = active
    line = next(line for line in page["lines"] if line["block_id"] == "lower_block")
    removed = line["word_ids"].pop()
    page["words"] = [word for word in page["words"] if word["id"] != removed]
    line["text"] = "Mot"
    assert v.validate_page(page) == []
    assert any("exact bound block text" in e for e in v.validate_text_provenance(page, texts))


def test_partial_word_slice_fails_exact_provenance(active):
    page, assets, texts = active
    sequence(page)["start"] = body_span(page)["start"] = 1  # A Unicode code point, not a byte.
    assert v.validate_page(page) == []
    assert v.validate_text_provenance(page, texts)
    assert v._content_source_errors(page, assets, texts)


def test_separate_body_spans_cannot_claim_one_sequence(active):
    page, _, _ = active
    span = body_span(page)
    span["block_ids"] = ["body"]
    page["provenance"]["text_spans"].append({**span, "block_ids": ["body_second"]})
    assert any("exactly one span" in e for e in v.validate_page(page))


def test_source_sequence_must_equal_its_body_span(active):
    page, _, _ = active
    sequence(page)["asset_id"] = "text_second"
    assert any("differs from its body span" in e for e in v.validate_page(page))


@pytest.mark.parametrize("field,value", [("role", "title"), ("role", "advertisement"),
                                          ("source_document_id", "other_document")])
def test_source_role_and_document_cannot_be_relabelled(active, field, value):
    page, assets, texts = active
    assets["text_body"]["metadata"][field] = value
    assert v._content_source_errors(page, assets, texts)


def test_title_cannot_be_folded_into_the_sequence_body(active):
    page, _, _ = active
    page["provenance"]["text_spans"] = [s for s in page["provenance"]["text_spans"]
                                         if s["block_ids"] != ["title"]]
    body_span(page)["block_ids"].insert(0, "title")
    assert any("exactly one span" in e for e in v.validate_page(page))


def test_title_source_must_remain_in_the_title_pool(active):
    page, assets, texts = active
    assets["text_title"]["metadata"]["role"] = "advertisement"
    assert any("separate title-role" in e for e in v._content_source_errors(page, assets, texts))


@pytest.mark.parametrize("aid", ["header", "ad"])
def test_sequence_forbidden_on_template_and_advertisement(active, aid):
    page, _, _ = active
    next(a for a in page["articles"] if a["id"] == aid)["extensions"] = {
        **next(a for a in page["articles"] if a["id"] == aid).get("extensions", {}),
        "mf:source_sequence": deepcopy(sequence(page)),
    }
    assert any("forbidden on template/non-body" in e for e in v.validate_page(page))


def test_each_body_needs_its_own_sequence(active):
    page, _, _ = active
    next(a for a in page["articles"] if a["id"] == "lower_story")["extensions"].pop("mf:source_sequence")
    assert any("lower_story" in e and "requires source_sequence" in e for e in v.validate_page(page))


def test_content_flag_cannot_describe_a_page_without_a_body(active):
    page, _, _ = active
    for block in page["blocks"]:
        if block["category"] == "texte":
            block["category"] = "annonce"
    for article in page["articles"]:
        article.get("extensions", {}).pop("mf:source_sequence", None)
    # Directly isolate the content check; layout independently forbids some such category changes.
    assert v._content_page_errors(page) == ["content: page requires at least one consecutive body article"]


@pytest.mark.parametrize("profile", [None, "unknown", "fr_press_19c_columns_4_6_measured"])
def test_reserved_markers_cannot_be_orphaned_or_downgraded(active, profile):
    page, _, _ = active
    if profile is None:
        page["provenance"]["parameters"].pop("content_profile")
    elif profile == "unknown":
        page["provenance"]["parameters"]["content_profile"] = profile
    else:
        page["profile"] = profile
    assert v.validate_page(page)


@pytest.mark.parametrize("field,value", [("unit_range", [True, 3]), ("unit_range", [0, 2, 3]),
                                          ("asset_id", "../text_body"), ("version", "2"),
                                          ("start", -1), ("unit_count", 2)])
def test_sequence_schema_refuses_malformed_or_extra_fields(active, field, value):
    page, _, _ = active
    sequence(page)[field] = value
    assert v.validate_page(page)


@pytest.mark.parametrize("mutation", [
    lambda r: r["documents"].pop(),
    lambda r: r["documents"].reverse(),
    lambda r: r["documents"].append(deepcopy(r["documents"][0])),
    lambda r: r["documents"][0].update(unit_count=3),
    lambda r: r["documents"][0].update(source_document_id="wrong"),
    lambda r: r["documents"][0].update(sha256="0" * 64),
    lambda r: r["documents"][-1].update(eligible=True, reason=None),
])
def test_receipt_recomputed_over_all_copied_body_documents(context, mutation):
    mutation(context[1]["extensions"]["mf:content_profile"])
    assert any("exact copied body" in e for e in v._load_content_profile(*context)[1])


@pytest.mark.parametrize("place", ["config", "receipt", "page_profile", "layout", "degradation"])
def test_context_markers_must_agree(context, place):
    root, manifest, _, _ = context
    config = json.loads((root / "config.json").read_text())
    if place == "config":
        config["render"].pop("content_profile")
    elif place == "receipt":
        manifest["extensions"].pop("mf:content_profile")
    elif place == "page_profile":
        manifest["profile"] = v.MEASURED_PROFILE
    else:
        config["render"].pop(f"{place}_profile")
    (root / "config.json").write_text(json.dumps(config))
    assert v._load_content_profile(*context)[1]


def test_no_eligible_copied_document_fails_even_with_a_consistent_receipt(context):
    root, manifest, assets, texts = context
    assets = {"text_short": assets["text_short"]}
    manifest["extensions"]["mf:content_profile"]["documents"] = [
        manifest["extensions"]["mf:content_profile"]["documents"][-1]
    ]
    assert v._load_content_profile(root, manifest, assets, texts)[1] == [
        "content: no copied body document has two complete units"
    ]


def test_resealed_receipt_cannot_alias_two_assets_to_one_document(context):
    _, manifest, assets, _ = context
    assets["text_second"]["metadata"]["source_document_id"] = "doc_text_body"
    manifest["extensions"]["mf:content_profile"]["documents"][1]["source_document_id"] = "doc_text_body"
    assert v._load_content_profile(*context)[1] == [
        "content: duplicate body source_document_id: doc_text_body"
    ]


def test_legacy_context_and_layout_page_do_not_acquire_content_requirements(context):
    root, manifest, assets, texts = context
    manifest["extensions"].pop("mf:content_profile")
    (root / "config.json").write_text("{}")
    assert v._load_content_profile(root, manifest, assets, texts) == (None, [])
    assert v.validate_page(fixture_page()) == []


@pytest.mark.parametrize("field,value", [("unit_count", True), ("eligible", 1),
                                          ("reason", "fallback"), ("extra", 0)])
def test_receipt_schema_is_strict(context, field, value):
    receipt = context[1]["extensions"]["mf:content_profile"]
    receipt["documents"][0][field] = value
    schema = v._schema("manifest").schema["properties"]["extensions"]["properties"]["mf:content_profile"]
    assert list(Draft202012Validator(schema).iter_errors(receipt))


def test_manifest_reserves_content_receipt_for_v2_schema_03(context):
    reference = {"path": "metadata.json", "sha256": "a" * 64}
    manifest = {
        "schema_version": "0.3.0", "dataset_id": "manual", "profile": v.LAYOUT_PROFILE,
        "generator": {"commit": "a" * 40, "dirty": True, "environment_path": "environment.json",
                      "environment_sha256": "a" * 64},
        "config": reference, "assets": reference,
        "rng": {"algorithm": "manual", "version": "1", "seed": 0},
        "calibration": {"protocol_path": "protocol.json", "protocol_sha256": "a" * 64,
                        "source_partitions": ["train", "dev"], "files_read": reference},
        "pages": [{"id": "p1", "path": "pages/p1.json", "sha256": "a" * 64,
                   "source_group_ids": ["manual_group"]}],
        "artifacts": [{**reference, "role": "fixture"}],
        "extensions": {"mf:content_profile": context[1]["extensions"]["mf:content_profile"],
                       "mf:degradation_profile": {"path": "provenance/degradation-profile.json", "sha256": "a" * 64}},
    }
    assert v._structural_errors(manifest, "manifest") == []
    for field, value in [("profile", v.MEASURED_PROFILE), ("schema_version", "0.2.0")]:
        altered = {**manifest, field: value}
        assert v._structural_errors(altered, "manifest")
