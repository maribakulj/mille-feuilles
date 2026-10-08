"""Consecutive source bodies through real font composition, without persisted rasters."""
from copy import deepcopy
import hashlib

import pytest

from mille_feuilles import degrade
from mille_feuilles.catalog import text_units
from mille_feuilles.pipeline import prepare_assets
from mille_feuilles.render import Composer, Config, PROFILE_LAYOUT


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    root = tmp_path_factory.mktemp("content-render")
    assets = prepare_assets(root, layout_profile=PROFILE_LAYOUT)
    yield root, assets
    assert not list(root.rglob("*.png"))


def composer(source, *, index=1, factor=1, profile="identity", enabled=True):
    root, assets = source
    degradation = degrade.load_profile(profile)
    degradation["oversampling"] = factor
    config = Config(width=1200, height=1656, dpi=67, columns=4, seed=20261007,
                    layout_profile=PROFILE_LAYOUT, degradation_profile=degradation,
                    content_profile="consecutive-v1" if enabled else None)
    return Composer(config, index, assets, root)


def reconstructed(composition, span):
    """Read the rendered words in span order, independently joining visible hyphens."""
    blocks = {b["id"]: b for b in composition.blocks}
    lines = {line["id"]: line for line in composition.lines}
    words = {word["id"]: word for word in composition.words}
    result, pending = [], None
    for bid in span["block_ids"]:
        for lid in blocks[bid]["line_ids"]:
            for wid in lines[lid]["word_ids"]:
                word = words[wid]
                hyphen = word.get("hyphenation")
                if hyphen and hyphen["part"] == "start":
                    assert pending is None and word["text"].endswith("-")
                    pending = (hyphen["group_id"], word["text"][:-1])
                elif hyphen and hyphen["part"] == "end":
                    assert pending is not None and pending[0] == hyphen["group_id"]
                    result.append(pending[1] + word["text"])
                    pending = None
                else:
                    assert pending is None
                    result.append(word["text"])
    assert pending is None
    return " ".join(result)


@pytest.fixture(scope="module")
def composed(source):
    output = composer(source)
    output._content_v2()
    return output


def test_every_multiunit_body_is_composed_whole_and_has_one_exact_source_span(source, composed):
    root, assets = source
    registry = {asset["id"]: asset for asset in assets}
    blocks = {block["id"]: block for block in composed.blocks}
    count = 0
    for article in composed.articles:
        receipt = article.get("extensions", {}).get("mf:source_sequence")
        body = [bid for bid in article["block_ids"] if blocks[bid]["category"] == "texte"]
        if article["id"] in composed.template_article_ids:
            assert receipt is None
            continue
        if not body:
            assert receipt is None
            continue
        count += 1
        assert receipt is not None and receipt["version"] == "1"
        asset = registry[receipt["asset_id"]]
        assert asset["metadata"]["role"] == "body"
        raw = (root / asset["path"]).read_text(encoding="utf-8")
        units = text_units(raw, "body")
        first, last = receipt["unit_range"]
        assert 0 <= first < last <= len(units) and last - first in (2, 3)
        assert receipt["start"] == units[first][1] and receipt["end"] == units[last - 1][2]
        spans = [span for span in composed.used_spans
                 if span["article_id"] == article["id"]
                 and registry[span["asset_id"]]["metadata"]["role"] == "body"]
        assert len(spans) == 1
        span = spans[0]
        assert span["block_ids"] == body
        assert span["asset_id"] == receipt["asset_id"]
        assert (span["start"], span["end"]) == (receipt["start"], receipt["end"])
        assert span["source_document_id"] == asset["metadata"]["source_document_id"]
        assert reconstructed(composed, span) == " ".join(raw[span["start"]:span["end"]].split())
        titles = [bid for bid in article["block_ids"] if blocks[bid]["category"] == "titre"]
        for title in titles:
            title_span = next(s for s in composed.used_spans if title in s["block_ids"])
            assert registry[title_span["asset_id"]]["metadata"]["role"] == "title"
            assert title_span["asset_id"] != span["asset_id"]
    assert count > 0
    assert any(len(span["block_ids"]) > 1 and registry[span["asset_id"]]["metadata"]["role"] == "body"
               for span in composed.used_spans)


def test_ineligible_body_cannot_eliminate_column_choices(source, composed):
    root, assets = source
    excluded = deepcopy(next(a for a in assets if a["kind"] == "text" and a["metadata"]["role"] == "body"))
    token = "9" * 400
    raw = token + "\n"
    excluded.update(id="text_ineligible", path="assets/texts/ineligible.txt",
                    sha256=hashlib.sha256(raw.encode()).hexdigest())
    excluded["metadata"]["source_document_id"] = "original_ineligible_fixture"
    path = root / excluded["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding="utf-8")
    value = composer((root, [*assets, excluded]))
    record = next(r for r in value.content_index["report"]["documents"] if r["asset_id"] == excluded["id"])
    assert not record["eligible"] and record["unit_count"] == 1
    assert token not in value._layout_unbreakable["body"]
    assert value.layout_draws == composed.layout_draws


@pytest.mark.parametrize("profile,factor", [("identity", 2), ("controlled-v1", 1)])
def test_composition_and_source_sequences_do_not_depend_on_photometry_or_sampling(
    source, composed, profile, factor,
):
    changed = composer(source, profile=profile, factor=factor)
    changed._content_v2()
    assert changed.used_spans == composed.used_spans
    assert changed.layout_plan == composed.layout_plan
    assert [a.get("extensions", {}).get("mf:source_sequence") for a in changed.articles] == [
        a.get("extensions", {}).get("mf:source_sequence") for a in composed.articles
    ]
    assert [(w["id"], w["text"], w["line_id"]) for w in changed.words] == [
        (w["id"], w["text"], w["line_id"]) for w in composed.words
    ]
    assert [(line["id"], line["text"], line["baseline"][0][1]) for line in changed.lines] == [
        (line["id"], line["text"], line["baseline"][0][1]) for line in composed.lines
    ]


def test_no_committed_body_is_an_error_even_with_an_eligible_pool(source, monkeypatch):
    value = composer(source)
    monkeypatch.setattr(value, "_v2_zone", lambda zone: None)
    with pytest.raises(ValueError, match="Aucun corps multi-unités"):
        value._content_v2()
    assert len(value.articles) == 1 and value.articles[0]["id"] in value.template_article_ids
    assert value.used_spans == []


def test_absent_option_keeps_the_old_config_and_never_indexes_body_documents(source, monkeypatch):
    from mille_feuilles import content

    def forbidden(*args, **kwargs):
        pytest.fail("Absent content option must not construct a new sampling pool")
    monkeypatch.setattr(content, "index_body_documents", forbidden)
    value = composer(source, enabled=False)
    value._content_v2()
    assert "content_profile" not in value.config.as_dict()
    assert all("mf:source_sequence" not in a.get("extensions", {}) for a in value.articles)


@pytest.mark.parametrize("change", [{"layout_profile": None}, {"degradation_profile": None},
                                    {"content_profile": "unknown"}])
def test_invalid_content_config_is_refused_before_composition(change):
    options = dict(layout_profile=PROFILE_LAYOUT, degradation_profile=degrade.load_profile("identity"),
                   content_profile="consecutive-v1")
    options.update(deepcopy(change))
    with pytest.raises(ValueError):
        Config(**options).validate()
