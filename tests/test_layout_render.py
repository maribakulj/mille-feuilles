"""Placement regressions and compact original-source v2 rendering checks."""

from copy import deepcopy
import math
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw
import pytest
from shapely.geometry import Polygon

from mille_feuilles import degrade, layout
from mille_feuilles.pipeline import prepare_assets
from mille_feuilles.render import Composer, Config, PROFILE_LAYOUT


def row(text="mot", bounds=None):
    return {"tokens": [{"text": text}], "font": None, "width": 100.0,
            "justify": False, "bounds": bounds or [0.0, -8.0, 50.0, 3.0]}


def composer():
    # _v2_fit is pure: no constructor, font, image, filesystem or random draw.
    return object.__new__(Composer)


def test_descenders_are_counted_before_crossing_column():
    fit = composer()._v2_fit([row("haut"), row("bas")], [],
                             [[0, 0, 100, 22], [110, 0, 210, 22]], (0, 0), 12)
    assert fit is not None
    assert [(r["column"], r["baseline"]) for r in fit["rows"]] == [(0, 8), (1, 8)]
    assert fit["cursor"] == (1, 18.2)
    assert all(r["baseline"] + r["bounds"][3] <= 22 for r in fit["rows"])


def test_exact_lower_bound_is_usable_without_clipping():
    fit = composer()._v2_fit([row()], [], [[0, 0, 100, 11]], (0, 0), 12)
    assert fit is not None
    assert fit["rows"][0]["baseline"] == 8


def test_complete_article_is_rejected_when_last_row_does_not_fit():
    assert composer()._v2_fit([row(), row()], [], [[0, 0, 100, 22]], (0, 0), 12) is None


def test_boxed_ad_moves_whole_to_next_column():
    fit = composer()._v2_fit([row("annonce")], [row("titre")],
                             [[0, 0, 100, 80], [110, 0, 210, 80]], (0, 60), 12, padding=4)
    assert fit is not None
    assert [r["column"] for r in fit["rows"]] == [1, 1]
    assert [r["kind"] for r in fit["rows"]] == ["heading", "body"]
    assert min(r["x"] + r["bounds"][0] for r in fit["rows"]) == 116
    assert min(r["baseline"] + r["bounds"][1] for r in fit["rows"]) == 6
    assert max(r["baseline"] + r["bounds"][3] for r in fit["rows"]) <= 74


def test_boxed_ad_never_flows_across_columns():
    rects = [[0, 0, 100, 40], [110, 0, 210, 40]]
    rows = [row(str(index)) for index in range(4)]
    assert composer()._v2_fit(rows, [], rects, (0, 0), 12, padding=4) is None
    assert composer()._v2_fit(rows, [], rects, (0, 0), 12) is not None


def test_heading_stays_with_first_body_row():
    fit = composer()._v2_fit([row("corps")], [row("titre")],
                             [[0, 0, 100, 80], [110, 0, 210, 80]], (0, 60), 12)
    assert fit is not None
    assert [(r["kind"], r["column"]) for r in fit["rows"]] == [("heading", 1), ("body", 1)]


def test_headline_span_cannot_borrow_an_unreserved_column():
    rects = [[0, 50, 100, 61], [110, 50, 210, 61], [220, 0, 320, 61]]
    rows = [row("un"), row("deux"), row("trois")]
    assert composer()._v2_fit(rows, [], rects[:2], (0, 50), 12) is None
    assert composer()._v2_fit(rows, [], rects, (0, 50), 12) is not None


def test_negative_left_bearing_is_shifted_inside_column():
    fit = composer()._v2_fit([row(bounds=[-2, -9, 50, 3])], [], [[25, 30, 125, 70]], (0, 30), 14)
    assert fit is not None
    line = fit["rows"][0]
    assert line["x"] == 27
    assert line["x"] + line["bounds"][0] == 25
    assert line["baseline"] + line["bounds"][1] == 30


def test_rejected_wrap_restores_size_and_hyphen_counter():
    obj = composer()
    obj.font_size, obj.hyphen_number = 18, 4

    def reject(*_args):
        obj.hyphen_number += 2
        raise ValueError("mot insécable")

    obj.wrap = reject
    with pytest.raises(ValueError, match="insécable"):
        obj._v2_rows("test", SimpleNamespace(size=10), 100, hyphenate=True, justify=True)
    assert (obj.font_size, obj.hyphen_number) == (18, 4)


def test_successful_wrap_reports_but_does_not_consume_hyphens():
    obj = composer()
    obj.font_size, obj.hyphen_number = 18, 4

    def wrapped(*_args):
        obj.hyphen_number += 1
        return [[{"text": "synthé-"}], [{"text": "tique"}]]

    obj.wrap = wrapped
    obj._v2_row_bounds = lambda *_args: [0, -8, 50, 3]
    planned, next_hyphen = obj._v2_rows(
        "synthétique", SimpleNamespace(size=10), 100, hyphenate=True, justify=True,
    )
    assert len(planned) == 2
    assert next_hyphen == 5
    assert (obj.font_size, obj.hyphen_number) == (18, 4)


def test_width_retry_reuses_hyphen_ids():
    obj = composer()
    obj.font_size, obj.hyphen_number = 18, 4
    attempts = []

    def wrapped(_text, _font, width, _hyphenate):
        attempts.append((width, obj.hyphen_number))
        obj.hyphen_number += 1
        return [[{"text": "exemple"}]]

    def bounds(_tokens, _font, width, _justify):
        return [0, -8, width + 2, 3]

    obj.wrap, obj._v2_row_bounds = wrapped, bounds
    _, next_hyphen = obj._v2_rows("exemple", SimpleNamespace(size=10), 100,
                                  hyphenate=True, justify=False)
    assert attempts == [(100, 4), (97, 4)]
    assert next_hyphen == 5
    assert obj.hyphen_number == 4


def test_column_filter_measures_tokens_without_wrapping_units():
    obj = composer()
    obj.layout_body_ratio = 20
    obj.layout_options = {"small_body_ratio": 0.82, "box_padding_px": [3, 6],
                          "boxed_ad_probability": 0.3}
    obj._layout_unbreakable = {"title": ["TITRE"], "body": ["court"], "advertisement": ["avis"]}
    obj._v2_font = lambda name, size: SimpleNamespace(name=name, size=size)
    obj._v2_word_bounds = lambda text, _font: (50, [0, -8, 90 if text == "TITRE" else 30, 3])

    def forbidden_wrap(*_args, **_kwargs):
        raise AssertionError("column_ok must not wrap complete source units")

    obj._v2_rows = forbidden_wrap
    # Maximal box padding reserves 16 px, so the 90 px title cannot fit 84 px.
    assert obj._v2_column_ok(100) is False
    obj.layout_options["boxed_ad_probability"] = 0
    assert obj._v2_column_ok(100) is True


def test_terminal_failures_are_separate_from_retries_before_success():
    obj = composer()
    obj.config = Config()
    zone = {"id": "main", "bbox": [0, 0, 100, 100], "columns": [[0, 100]],
            "headline_span": None, "headline_reserved": None, "headline_body_band": None}
    obj.layout_plan = {"zones": [zone]}
    obj.articles = []
    obj.layout_rejected_candidates = {"headline": 0, "boxed_ad": 0, "ordinary": 0}
    obj.layout_termination_rejections = {}
    obj.rng = SimpleNamespace(random=lambda: 1.0, choice=lambda choices: choices[0])
    obj.role_units = {"body": [(None, "corps complet", 0, 13)], "title": [(None, "Titre", 0, 5)]}
    obj._v2_type = lambda *_args: ({}, None, 12)
    obj._v2_rows = lambda *_args, **_kwargs: ([row()], 0)
    fit_results = iter([None, {"rows": [row()], "cursor": (0, 100)}] + [None] * 32)
    obj._v2_fit = lambda *_args: next(fit_results)
    obj._v2_commit = lambda candidate: obj.articles.append(candidate)
    obj._v2_zone(zone)
    assert len(obj.articles) == 1
    assert obj.layout_rejected_candidates == {"headline": 0, "boxed_ad": 0, "ordinary": 1}
    assert obj.layout_termination_rejections == {"main": 32}


def test_balanced_headline_uses_every_column_and_preserves_complete_text_order():
    rows = [row(str(index)) for index in range(7)]
    rects = [[0, 20, 100, 100], [110, 20, 210, 100], [220, 20, 320, 100]]
    fit = composer()._v2_balance(rows, rects, 12)
    assert fit is not None
    assert [sum(r["column"] == column for r in fit["rows"]) for column in range(3)] == [3, 2, 2]
    assert [r["tokens"][0]["text"] for r in fit["rows"]] == [str(i) for i in range(7)]
    assert fit["bottom"] == 55
    assert all(r["baseline"] + r["bounds"][1] >= 20 for r in fit["rows"])


def test_balanced_headline_requires_two_lines_in_every_reserved_column():
    rects = [[0, 20, 100, 100], [110, 20, 210, 100], [220, 20, 320, 100]]
    assert composer()._v2_balance([row()] * 5, rects, 12) is None


def test_balanced_headline_refuses_an_overflowing_column_without_truncation():
    rects = [[0, 20, 100, 50], [110, 20, 210, 100]]
    assert composer()._v2_balance([row()] * 5, rects, 12) is None


def test_lower_zone_column_filter_uses_main_body_size():
    obj = composer()
    obj.layout_body_ratio = 20
    obj.layout_options = {"small_body_ratio": 0.82, "box_padding_px": [3, 6],
                          "boxed_ad_probability": 0.3}
    obj._layout_unbreakable = {"title": ["Titre"], "body": ["corps"], "advertisement": ["avis"]}
    font_sizes = []

    def font(name, size):
        font_sizes.append((name, size))
        return SimpleNamespace(name=name, size=size)

    obj._v2_font = font
    obj._v2_word_bounds = lambda *_args: (30, [0, -8, 30, 3])
    assert obj._v2_column_ok(300, 200)
    assert font_sizes == [("OldStandard-Regular.ttf", 10), ("OldStandard-Bold.ttf", 12)]


@pytest.fixture(scope="module")
def layout_assets(tmp_path_factory):
    root = tmp_path_factory.mktemp("layout_render")
    source = root / "source"
    source.mkdir()
    assets = prepare_assets(source, layout_profile=PROFILE_LAYOUT)
    yield root, source, assets
    assert sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) < 20 * 1024**2
    assert not list(root.rglob("*.png")), "Composition checks must not persist rasters"


def real_composer(fixture, *, width=1200, height=1656, columns=4, index=1,
                  profile="identity", factor=1):
    _, source, assets = fixture
    degradation = degrade.load_profile(profile)
    degradation["oversampling"] = factor
    return Composer(Config(width=width, height=height, columns=columns, seed=20261007,
                           degradation_profile=degradation, layout_profile=PROFILE_LAYOUT),
                    index, assets, source)


@pytest.fixture(scope="module", params=[
    (1200, 1656, 4, 1), (800, 1100, 5, 0), (1200, 1656, 6, 2), (800, 1100, None, 0),
], ids=["wide-title-lower-zone", "small-five-columns", "six-columns", "small-auto"])
def layout_composition(layout_assets, request):
    width, height, columns, index = request.param
    comp = real_composer(layout_assets, width=width, height=height, columns=columns, index=index)
    comp._content_v2()
    yield comp
    comp.canvas.close()


def reconstructed_span(comp, span):
    blocks = {b["id"]: b for b in comp.blocks}
    lines = {line["id"]: line for line in comp.lines}
    words = {word["id"]: word for word in comp.words}
    selected = [words[wid] for bid in span["block_ids"] for lid in blocks[bid]["line_ids"]
                for wid in lines[lid]["word_ids"]]
    parts, index = [], 0
    while index < len(selected):
        word = selected[index]
        hyphen = word["hyphenation"]
        if hyphen is None:
            parts.append(word["text"])
            index += 1
            continue
        assert hyphen["part"] == "start"
        assert index + 1 < len(selected)
        following = selected[index + 1]
        assert following["hyphenation"]["part"] == "end"
        assert following["hyphenation"]["group_id"] == hyphen["group_id"]
        assert word["text"].endswith("-")
        joined = word["text"][:-1] + following["text"]
        assert joined == hyphen["reconstructed_text"] == following["hyphenation"]["reconstructed_text"]
        parts.append(joined)
        index += 2
    return " ".join(parts)


def test_real_composition_preserves_complete_original_spans_and_article_order(layout_composition):
    comp = layout_composition
    assert layout.check_plan(comp.layout_plan) == []
    assets = {a["id"]: a for a in comp.assets}
    for span in comp.used_spans:
        raw = (comp.asset_root / assets[span["asset_id"]]["path"]).read_text(encoding="utf-8")
        assert reconstructed_span(comp, span) == " ".join(raw[span["start"]:span["end"]].split())
    assert [bid for a in comp.articles for bid in a["block_ids"]] == [
        b["id"] for b in comp.blocks if b["line_ids"]
    ]
    zones = [a["extensions"]["mf:layout"]["zone_id"] for a in comp.articles
             if a["id"] not in comp.template_article_ids]
    assert zones == sorted(zones, key={"main": 0, "rez_de_chaussee": 1}.get)
    main_typography = comp.layout_typography["main"]
    assert all(typo == main_typography for typo in comp.layout_typography.values())
    assert comp.layout_termination_rejections == {z["id"]: 32 for z in comp.layout_plan["zones"]}


def test_real_rules_never_intersect_text_and_frames_follow_exact_envelopes(layout_composition):
    comp = layout_composition
    blocks = {block["id"]: block for block in comp.blocks}
    text = [Polygon(block["polygon"]) for block in comp.blocks if block["line_ids"]]
    for block in comp.blocks:
        if block["category"] == "separateur":
            rule = Polygon(block["polygon"])
            assert max((rule.intersection(poly).area for poly in text), default=0) <= 1e-6, block["id"]
    for article in comp.articles:
        if article["id"] in comp.template_article_ids:
            continue
        meta = article["extensions"]["mf:layout"]
        normal = comp.layout_typography[meta["zone_id"]]["normal_body_size"]
        assert meta["small_body"] == (meta["body_font_size"] < normal)
        if not meta["small_body_requested"]:
            assert meta["body_font_size"] == normal
        frame = meta["box"]
        if frame is None:
            continue
        ink = [point for bid in article["block_ids"] for point in blocks[bid]["polygon"]]
        x0, y0, x1, y1 = frame["bbox"]
        inset = frame["padding"] + 2
        assert [min(x for x, _ in ink), min(y for _, y in ink),
                max(x for x, _ in ink), max(y for _, y in ink)] == pytest.approx(
                    [x0 + inset, y0 + inset, x1 - inset, y1 - inset])
        assert len(frame["rule_ids"]) == 4
        assert all(blocks[identity]["article_id"] is None for identity in frame["rule_ids"])


def test_real_headline_body_is_balanced_and_later_articles_stay_below_band(layout_composition):
    comp = layout_composition
    blocks = {block["id"]: block for block in comp.blocks}
    for zone in comp.layout_plan["zones"]:
        if zone["headline_span"] is None:
            continue
        articles = [a for a in comp.articles if a.get("extensions", {}).get("mf:layout", {}).get("zone_id") == zone["id"]]
        head = articles[0]
        meta = head["extensions"]["mf:layout"]["headline"]
        assert meta is not None and meta["block_id"] == head["block_ids"][0]
        assert meta["reservation_bbox"] == zone["headline_reserved"]
        title = Polygon(blocks[meta["block_id"]]["polygon"])
        assert title.bounds[2] - title.bounds[0] > zone["columns"][0][1] - zone["columns"][0][0] + comp.gutter
        span = zone["headline_span"]
        bodies = [blocks[bid] for bid in head["block_ids"] if bid != meta["block_id"]]
        assert len(bodies) == span
        counts = [len(block["line_ids"]) for block in bodies]
        assert min(counts) >= 2 and max(counts) - min(counts) <= 1
        assert meta["body_column_indices"] == list(range(span))
        band = zone["headline_body_band"]
        for index, block in enumerate(bodies):
            x0, y0, x1, y1 = Polygon(block["polygon"]).bounds
            assert x0 >= zone["columns"][index][0] - 1e-6
            assert x1 <= zone["columns"][index][1] + 1e-6
            assert y0 >= band[1] - 1e-6 and y1 < band[3]
        for article in articles[1:]:
            for bid in article["block_ids"]:
                x0, y0, x1, _ = Polygon(blocks[bid]["polygon"]).bounds
                if x1 <= band[2] + 1e-6:
                    assert x0 >= band[0] - 1e-6 and y0 >= band[3] - 1e-6


def test_real_coverage_stays_in_annotation_support(layout_composition):
    comp = layout_composition
    support = Image.new("1", comp.canvas.size)
    draw = ImageDraw.Draw(support)
    polygons = [word["polygon"] for word in comp.words]
    polygons += [block["polygon"] for block in comp.blocks if not block["line_ids"]]
    for polygon in polygons:
        draw.rectangle((math.floor(min(x for x, _ in polygon)), math.floor(min(y for _, y in polygon)),
                        math.ceil(max(x for x, _ in polygon)), math.ceil(max(y for _, y in polygon))), fill=1)
    escaped = (np.asarray(comp.canvas) > 0) & ~np.asarray(support, dtype=bool)
    assert not escaped.any(), int(escaped.sum())


def test_real_wide_layout_is_exercised_not_only_optional_branches(layout_composition):
    comp = layout_composition
    if (comp.config.width, comp.config.columns, comp.index) != (1200, 4, 1):
        return
    variants = [a["extensions"]["mf:layout"] for a in comp.articles if "extensions" in a]
    assert len(comp.layout_plan["zones"]) == 2
    assert sum(meta["headline"] is not None for meta in variants) == 1
    assert any(meta["box"] is not None for meta in variants)
    assert any(meta["small_body"] for meta in variants)
    assert len({meta["body_font_size"] for meta in variants}) >= 2


def test_real_profiles_and_sampling_keep_pen_positions_wraps_sources_and_band(layout_assets, monkeypatch):
    original = Composer.add_line
    captured = []

    def observe(self, tokens, block, x, baseline, font, width, justify=False):
        captured.append((deepcopy(tokens), block["id"], x, baseline, font.size, width, justify))
        return original(self, tokens, block, x, baseline, font, width, justify)

    monkeypatch.setattr(Composer, "add_line", observe)
    reference = None
    for profile, factor in (("identity", 1), ("controlled-v1", 1), ("identity", 2)):
        comp = real_composer(layout_assets, profile=profile, factor=factor)
        captured.clear()
        comp._content_v2()
        observed = {"pens": deepcopy(captured), "spans": deepcopy(comp.used_spans),
                    "layout": deepcopy(comp.layout_plan), "type": deepcopy(comp.layout_typography),
                    "words": [word["text"] for word in comp.words]}
        if reference is None:
            reference = observed
        else:
            assert observed == reference
        comp.canvas.close()


def test_small_six_column_title_failure_is_controlled_before_raster_allocation(layout_assets, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Incompatible explicit columns must fail before raster allocation")

    monkeypatch.setattr(Image, "new", forbidden)
    with pytest.raises(layout.LayoutError, match="aucune option de colonnes"):
        real_composer(layout_assets, width=800, height=1100, columns=6, index=0)
