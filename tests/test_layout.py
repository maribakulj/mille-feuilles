"""Pure v2 layout planner: declared options, fixed draw order, checked geometry."""

import math
import random
from copy import deepcopy

import pytest

from mille_feuilles.layout import (
    DEFAULT_OPTIONS,
    MIN_BODY_PX,
    LayoutError,
    check_options,
    check_plan,
    columns_below,
    draw_layout,
    headline_rect,
    place_zones,
    headline_columns,
    reserve_headline,
    reserve_headline_band,
    small_body_size,
)

PAGE = dict(width=2680, height=3698, margin=94, gutter=24.0)


def always(_width):
    return True


def plan_for(seed, width=2680, margin=94, gutter=24.0, options=None, top=330.0, bottom=3604.0, height=3698):
    draws = draw_layout(random.Random(seed), options or DEFAULT_OPTIONS, width=width, height=height,
                        margin=margin, gutter=gutter, column_ok=always)
    return place_zones(draws, top=top, bottom=bottom, min_zone_height=150.0)


def test_default_options_are_valid_and_returned_unchanged():
    options = deepcopy(DEFAULT_OPTIONS)
    assert check_options(options) is options and options == DEFAULT_OPTIONS


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o.pop("headline_probability"),
        lambda o: o.update(extra=1),
        lambda o: o.update(headline_probability=1.5),
        lambda o: o.update(headline_probability=float("nan")),
        lambda o: o.update(rez_de_chaussee_probability=True),
        lambda o: o["main_columns"].update(weights=[1, 2]),
        lambda o: o["main_columns"].update(weights=[1, 0, 1]),
        lambda o: o["main_columns"].update(choice=[4, 4, 6]),
        lambda o: o["main_columns"].update(choice=[1, 5, 6]),
        lambda o: o["main_columns"].update(choice=[]),
        lambda o: o["headline_span"].update(choice=[1, 2]),
        lambda o: o.update(rez_de_chaussee_share=[0.35, 0.20]),
        lambda o: o.update(rez_de_chaussee_share=[0.2, 0.9]),
        lambda o: o.update(box_padding_px=[3.5, 6]),
        lambda o: o.update(small_body_ratio=0.5),
        lambda o: o.update(small_body_ratio=10**400),
        lambda o: o["small_body_probability"].pop("advertisement"),
        lambda o: o.update(zone_gap_px=2),
    ],
)
def test_invalid_options_are_refused(mutate):
    options = deepcopy(DEFAULT_OPTIONS)
    mutate(options)
    with pytest.raises(LayoutError):
        check_options(options)


def test_draw_order_is_fixed_and_deterministic():
    a = draw_layout(random.Random(5), DEFAULT_OPTIONS, column_ok=always, **PAGE)
    b = draw_layout(random.Random(5), DEFAULT_OPTIONS, column_ok=always, **PAGE)
    assert a == b
    # The documented order, replayed by hand on the same stream.
    rng = random.Random(5)
    main = rng.choices([4, 5, 6], [1, 3, 6])[0]
    has_rdc = rng.random() < 0.5
    if has_rdc:
        share = rng.uniform(0.20, 0.35)
        rdc = rng.choices([3, 4, 5, 6], [1, 2, 2, 1])[0]
    has_headline = rng.random() < 0.4
    assert len(a["zones"][0]["columns"]) == main
    assert (len(a["zones"]) == 2) == has_rdc
    if has_rdc:
        assert a["rez_de_chaussee_share"] == share and len(a["zones"][1]["columns"]) == rdc
    assert (a["zones"][0]["headline_span"] is not None) == (has_headline and main >= 3)


def test_planner_consumes_only_the_stream_it_is_given():
    random.seed(1)
    before = random.random()
    random.seed(1)
    draw_layout(random.Random(9), DEFAULT_OPTIONS, column_ok=always, **PAGE)
    assert random.random() == before


def test_valid_plans_over_many_seeds_and_widths():
    seen = {"rdc": 0, "headline": 0}
    for width, margin, gutter in ((2680, 94, 24.0), (1200, 42, 10.0), (4000, 140, 35.0)):
        for seed in range(200):
            height = round(width * 1.38)
            plan = plan_for(seed, width, margin, gutter, top=width * 0.12, bottom=height - margin, height=height)
            assert check_plan(plan) == []
            seen["rdc"] += len(plan["zones"]) == 2
            seen["headline"] += plan["zones"][0]["headline_span"] is not None
            for zone in plan["zones"]:
                assert zone["columns"][0][0] == margin
                assert math.isclose(zone["columns"][-1][1], width - margin, abs_tol=1e-6)
    assert 0 < seen["rdc"] < 600 and 0 < seen["headline"] < 600


def test_column_ok_removes_options_before_drawing():
    # Only widths of at least 550 px fit: 4 columns at 2680 px (≈ 605 px), not 5 or 6.
    for seed in range(50):
        draws = draw_layout(random.Random(seed), DEFAULT_OPTIONS, column_ok=lambda w: w >= 550, **PAGE)
        assert len(draws["zones"][0]["columns"]) == 4


def test_no_fitting_column_option_is_a_controlled_error():
    with pytest.raises(LayoutError, match="aucune option de colonnes"):
        draw_layout(random.Random(0), DEFAULT_OPTIONS, column_ok=lambda w: False, **PAGE)


def test_headline_span_is_clamped_and_absent_below_three_columns():
    options = deepcopy(DEFAULT_OPTIONS)
    options.update(headline_probability=1.0, main_columns={"choice": [3], "weights": [1]},
                   headline_span={"choice": [5], "weights": [1]})
    draws = draw_layout(random.Random(0), options, column_ok=always, **PAGE)
    assert draws["zones"][0]["headline_span"] == 2
    options["main_columns"] = {"choice": [2], "weights": [1]}
    assert draw_layout(random.Random(0), options, column_ok=always, **PAGE)["zones"][0]["headline_span"] is None


def forced(rdc=True, headline=True):
    options = deepcopy(DEFAULT_OPTIONS)
    options.update(rez_de_chaussee_probability=1.0 if rdc else 0.0,
                   headline_probability=1.0 if headline else 0.0)
    return plan_for(3, options=options)


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda p: p["zones"][1]["bbox"].__setitem__(1, p["zones"][0]["bbox"][3] - 5), "chevauchent"),
        (lambda p: p["zones"][0]["columns"][0].__setitem__(0, 10), "hors de la zone"),
        (lambda p: p["zones"][0]["columns"][1].__setitem__(0, p["zones"][0]["columns"][0][1] + 1), "gouttière"),
        (lambda p: p["zones"][1].update(headline_span=2), "titre large"),
        (lambda p: p["zones"][0].update(headline_span=len(p["zones"][0]["columns"])), "titre large"),
        (lambda p: p["zone_rules"].clear(), "filet"),
        (lambda p: p["zone_rules"][0].__setitem__(3, p["zone_rules"][0][1] + 1), "filet"),
        (lambda p: p["zones"][0]["bbox"].__setitem__(0, float("nan")), "non finis"),
        (lambda p: p["zones"].reverse(), "zones attendues"),
        (lambda p: p.update(version="2"), "version"),
        (lambda p: p["zones"][0].pop("columns"), "clés"),
        (lambda p: p.update(min_zone_height=10**6), "trop basse"),
        (lambda p: p.update(height=int(p["zones"][1]["bbox"][3])), "hors page"),
    ],
)
def test_check_plan_detects_mutations(mutate, expected):
    plan = forced()
    assert check_plan(plan) == []
    mutate(plan)
    errors = check_plan(plan)
    assert errors and any(expected in e for e in errors), errors


def test_zone_rule_is_full_width_between_zones():
    plan = forced()
    (x0, y0, x1, y1), = plan["zone_rules"]
    main, rdc = plan["zones"]
    assert main["bbox"][3] <= y0 < y1 <= rdc["bbox"][1] and y1 - y0 == 2
    assert x0 == main["bbox"][0] and x1 == main["bbox"][2]


def test_headline_reservation_and_columns_below():
    plan = forced(rdc=False)
    zone = plan["zones"][0]
    span = zone["headline_span"]
    x0, y0, x1, y1 = headline_rect(plan, "main")
    assert (x0, x1) == (zone["columns"][0][0], zone["columns"][span - 1][1]) and (y0, y1) == tuple(zone["bbox"][1::2])
    with pytest.raises(LayoutError, match="bande du titre large doit être réservée"):
        columns_below(plan, "main")
    reserved = reserve_headline(plan, "main", headline_bottom=y0 + 120, gap=10)
    assert plan["zones"][0]["headline_reserved"] is None  # input plan unchanged
    assert reserved["zones"][0]["headline_reserved"] == [x0, y0, x1, y0 + 130]
    assert check_plan(reserved) == []
    with pytest.raises(LayoutError, match="bande"):
        columns_below(reserved, "main")
    covered = headline_columns(reserved, "main")
    assert len(covered) == span and [r[1] for r in covered] == [y0 + 130] * span
    assert [r[0] for r in covered] == [c[0] for c in zone["columns"][:span]]
    banded = reserve_headline_band(reserved, "main", body_flow_bottom=y0 + 400, gap=8, min_space_below=20)
    rects = columns_below(banded, "main")
    assert [r[1] for r in rects[:span]] == [y0 + 408] * span
    assert all(r[1] == y0 for r in rects[span:])
    assert all(r[3] == y1 for r in rects)
    with pytest.raises(LayoutError, match="déjà réservé"):
        reserve_headline(reserved, "main", headline_bottom=y0 + 100, gap=10)
    with pytest.raises(LayoutError, match="remplit"):
        reserve_headline(plan, "main", headline_bottom=y1 - 5, gap=10)
    with pytest.raises(LayoutError):
        headline_rect(forced(headline=False), "main")
    with pytest.raises(LayoutError):
        columns_below(plan, "absent")


def banded_plan():
    plan = forced(rdc=False)
    y0 = plan["zones"][0]["bbox"][1]
    plan = reserve_headline(plan, "main", headline_bottom=y0 + 120, gap=10)
    return reserve_headline_band(plan, "main", body_flow_bottom=y0 + 400, gap=8, min_space_below=20)


def test_headline_band_is_recorded_aligned_and_valid():
    plan = banded_plan()
    zone = plan["zones"][0]
    rx0, _, rx1, ry1 = zone["headline_reserved"]
    assert zone["headline_body_band"] == [rx0, ry1, rx1, zone["bbox"][1] + 408]
    assert check_plan(plan) == []


def test_headline_band_refusals():
    plan = forced(rdc=False)
    y0, y1 = plan["zones"][0]["bbox"][1], plan["zones"][0]["bbox"][3]
    with pytest.raises(LayoutError, match="réservé avant"):
        headline_columns(plan, "main")
    with pytest.raises(LayoutError):
        reserve_headline_band(plan, "main", body_flow_bottom=y0 + 400, gap=8, min_space_below=20)
    reserved = reserve_headline(plan, "main", headline_bottom=y0 + 120, gap=10)
    with pytest.raises(LayoutError, match="espace minimal"):
        reserve_headline_band(reserved, "main", body_flow_bottom=y1 - 10, gap=8, min_space_below=20)
    for bad in (dict(body_flow_bottom=y0 + 100, gap=8, min_space_below=20),   # above the reservation
                dict(body_flow_bottom=y0 + 400, gap=-1, min_space_below=20),
                dict(body_flow_bottom=y0 + 400, gap=8, min_space_below=0),
                dict(body_flow_bottom=float("nan"), gap=8, min_space_below=20)):
        with pytest.raises(LayoutError):
            reserve_headline_band(reserved, "main", **bad)
    banded = reserve_headline_band(reserved, "main", body_flow_bottom=y0 + 400, gap=8, min_space_below=20)
    assert reserved["zones"][0]["headline_body_band"] is None  # input unchanged
    with pytest.raises(LayoutError, match="déjà réservée"):
        reserve_headline_band(banded, "main", body_flow_bottom=y0 + 500, gap=8, min_space_below=20)
    with pytest.raises(LayoutError, match="déjà réservée"):
        headline_columns(banded, "main")
    with pytest.raises(LayoutError):
        reserve_headline_band(forced(headline=False), "main", body_flow_bottom=500, gap=8, min_space_below=20)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda z: z["headline_body_band"].__setitem__(2, z["columns"][-1][1]),   # wider than the reservation
        lambda z: z["headline_body_band"].__setitem__(1, z["headline_reserved"][3] + 1),  # detached
        lambda z: z["headline_body_band"].__setitem__(3, z["bbox"][3] + 1),       # below the zone
        lambda z: z["headline_body_band"].__setitem__(3, z["headline_body_band"][1]),  # empty
        lambda z: z.update(headline_body_band="x"),
        lambda z: z.update(headline_body_band=[1, 2, 3]),
        lambda z: z["headline_body_band"].__setitem__(0, float("nan")),
        lambda z: z.update(headline_reserved=None),
        lambda z: z.update(headline_span=None),
        lambda z: z.update(headline_span="2"),
        lambda z: z.pop("headline_body_band"),
    ],
)
def test_check_plan_detects_invalid_headline_bands(mutate):
    plan = banded_plan()
    mutate(plan["zones"][0])
    assert check_plan(plan)  # never raises


@pytest.mark.parametrize(
    "mutate",
    [
        lambda z: z["headline_reserved"].__setitem__(2, z["columns"][-1][1]),   # wider than its span
        lambda z: z["headline_reserved"].__setitem__(1, z["bbox"][1] + 5),       # not at zone top
        lambda z: z["headline_reserved"].__setitem__(3, z["bbox"][3] + 1),       # below the zone
        lambda z: z.update(headline_span=None),                                 # reservation without span
        lambda z: z.pop("headline_reserved"),
    ],
)
def test_check_plan_detects_invalid_headline_reservations(mutate):
    plan = forced(rdc=False)
    y0 = plan["zones"][0]["bbox"][1]
    plan = reserve_headline(plan, "main", headline_bottom=y0 + 120, gap=10)
    mutate(plan["zones"][0])
    assert check_plan(plan)


def test_rez_de_chaussee_column_count_always_differs_from_main():
    options = deepcopy(DEFAULT_OPTIONS)
    options["rez_de_chaussee_probability"] = 1.0
    for seed in range(200):
        zones = draw_layout(random.Random(seed), options, column_ok=always, **PAGE)["zones"]
        assert len(zones[0]["columns"]) != len(zones[1]["columns"])
    options.update(main_columns={"choice": [4], "weights": [1]},
                   rez_de_chaussee_columns={"choice": [4], "weights": [1]})
    with pytest.raises(LayoutError, match="différent de main"):
        draw_layout(random.Random(0), options, column_ok=always, **PAGE)


def test_check_plan_rejects_equal_column_counts_and_vertical_overflow():
    plan = forced()
    plan["zones"][1]["columns"] = deepcopy(plan["zones"][0]["columns"])
    assert any("même nombre" in e for e in check_plan(plan))
    plan = forced(rdc=False, headline=False)
    plan["zones"][0]["bbox"][3] = plan["height"] - plan["margin"] + 1
    assert any("hors page" in e for e in check_plan(plan))


def test_place_zones_refuses_bounds_outside_page_margins():
    draws = draw_layout(random.Random(0), DEFAULT_OPTIONS, column_ok=always, **PAGE)
    with pytest.raises(LayoutError, match="marges"):
        place_zones(draws, top=330.0, bottom=3698.0, min_zone_height=150.0)
    with pytest.raises(LayoutError, match="marges"):
        place_zones(draws, top=10.0, bottom=3604.0, min_zone_height=150.0)


def test_columns_below_without_headline_starts_at_zone_top():
    plan = forced(headline=False)
    rects = columns_below(plan, "rez_de_chaussee")
    assert all(r[1] == plan["zones"][1]["bbox"][1] for r in rects)


@pytest.mark.parametrize("normal", [10, 11, 12, 13, 20, 23, 40])
def test_small_body_never_below_profile_minimum(normal):
    small = small_body_size(normal, 0.82)
    assert MIN_BODY_PX <= small <= normal
    if normal <= 12:
        assert small == MIN_BODY_PX
    assert (small == normal) == (normal == MIN_BODY_PX)  # inactive only at normal = 10


def test_small_body_exact_examples_distinguish_clamp_and_inactivity():
    # normal -> requested round(normal * 0.82) -> effective
    # 10 -> 8 -> 10 (clamped, inactive); 11 -> 9 -> 10 (clamped, active); 12 -> 10 -> 10 (not clamped, active)
    for normal, requested, clamped, active in ((10, 8, True, False), (11, 9, True, True), (12, 10, False, True)):
        assert round(normal * 0.82) == requested
        effective = small_body_size(normal, 0.82)
        assert effective == 10
        assert (requested < MIN_BODY_PX) == clamped
        assert (effective != normal) == active


@pytest.mark.parametrize("args", [(9, 0.82), (True, 0.82), (12.0, 0.82), (12, 0.5), (12, float("inf"))])
def test_small_body_size_rejects_invalid_inputs(args):
    with pytest.raises(LayoutError):
        small_body_size(*args)


@pytest.mark.parametrize(
    "kwargs",
    [dict(width=0, margin=0, gutter=1.0), dict(width=100, margin=60, gutter=1.0),
     dict(width=1000, margin=10, gutter=-1.0), dict(width=1000.0, margin=10, gutter=1.0),
     dict(width=1000, height=15, margin=10, gutter=1.0), dict(width=1000, height=1400.0, margin=10, gutter=1.0)],
)
def test_invalid_page_geometry_is_refused(kwargs):
    kwargs = {"height": 1400, **kwargs}
    with pytest.raises(LayoutError):
        draw_layout(random.Random(0), DEFAULT_OPTIONS, column_ok=always, **kwargs)


def test_zone_too_low_for_its_body_is_refused():
    draws = draw_layout(random.Random(0), DEFAULT_OPTIONS, column_ok=always, **PAGE)
    with pytest.raises(LayoutError, match="trop basse"):
        place_zones(draws, top=330.0, bottom=500.0, min_zone_height=300.0)


def test_global_rng_is_rejected():
    with pytest.raises(LayoutError):
        draw_layout(random, DEFAULT_OPTIONS, column_ok=always, **PAGE)



# --- probes of the adversarial review (Codex, planner-probes.json) -----------


@pytest.mark.parametrize("plan", [None, [], "plan", 3])
def test_check_plan_on_non_objects_returns_errors(plan):
    assert check_plan(plan)


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda p: p.update(extra=1), "clés"),
        (lambda p: p["zones"][0].update(extra=1), "clés"),
        (lambda p: p.update(rez_de_chaussee_share=float("nan")), "rez_de_chaussee_share"),
        (lambda p: p.update(rez_de_chaussee_share=None), "rez_de_chaussee_share"),
        (lambda p: p.pop("rez_de_chaussee_share"), "clés"),
        (lambda p: p.update(rez_de_chaussee_share=0.9), "incohérent"),
        (lambda p: p["zones"][0]["bbox"].__setitem__(1, -100), "hors page"),
        (lambda p: p.update(min_zone_height=-100), "min_zone_height"),
        (lambda p: p.update(gutter=-24), "gutter"),
        (lambda p: p["zone_rules"][0].__setitem__(0, -100), "filet"),
        (lambda p: p["zone_rules"][0].__setitem__(2, 3000), "filet"),
        (lambda p: p["zones"][1].update(columns=p["zones"][1]["columns"][:1]), "deux colonnes"),
        (lambda p: p.update(width=10**400), "width"),
        (lambda p: p.update(width=2680.0), "width"),
        (lambda p: p.update(margin=-1), "margin"),
        (lambda p: p["zones"][0].update(bbox=[1, 2, 3]), "bbox"),
        (lambda p: p.update(zones={}), "zones"),
        (lambda p: p.update(zone_rules=None), "zone_rules"),
    ],
)
def test_check_plan_probe_cases_are_controlled_errors(mutate, expected):
    plan = forced()
    mutate(plan)
    errors = check_plan(plan)
    assert errors and any(expected in e for e in errors), errors


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o["main_columns"].update(choice=[[4], 5, 6]),
        lambda o: o["main_columns"].update(choice={"a": 1}),
        lambda o: o["main_columns"].update(weights=[1e308, 1e308, 1e308]),
        lambda o: o["main_columns"].update(weights=[10**400, 1, 1]),
        lambda o: o.update(main_columns=[4, 5, 6]),
    ],
)
def test_check_options_probe_cases_are_controlled_errors(mutate):
    options = deepcopy(DEFAULT_OPTIONS)
    mutate(options)
    with pytest.raises(LayoutError):
        check_options(options)


@pytest.mark.parametrize("width, height", [(10**400, 3698), (2680, 10**400), (50, 3698), (2680, 30000)])
def test_draw_layout_refuses_out_of_range_page_sizes(width, height):
    with pytest.raises(LayoutError):
        draw_layout(random.Random(0), DEFAULT_OPTIONS, width=width, height=height, margin=94, gutter=24.0,
                    column_ok=always)



@pytest.mark.parametrize("span", ["2", 2.0, {}, [], True, -1, 0, 1, 99, None])
def test_invalid_span_with_active_reservation_is_a_controlled_error(span):
    plan = forced(rdc=False)
    y0 = plan["zones"][0]["bbox"][1]
    plan = reserve_headline(plan, "main", headline_bottom=y0 + 140, gap=10)
    plan["zones"][0]["headline_span"] = span
    errors = check_plan(plan)  # must never raise
    assert errors and any("titre large" in e or "réservation" in e for e in errors), errors


@pytest.mark.parametrize("reserved", ["x", [1, 2, 3], [float("nan")] * 4, {}, [None] * 4])
def test_malformed_reservation_is_a_controlled_error(reserved):
    plan = forced(rdc=False)
    y0 = plan["zones"][0]["bbox"][1]
    plan = reserve_headline(plan, "main", headline_bottom=y0 + 140, gap=10)
    plan["zones"][0]["headline_reserved"] = reserved
    assert check_plan(plan)



# --- shared body size: the rez-de-chaussée filter knows the main width -----------


def test_rdc_column_ok_receives_the_recorded_main_width_and_filters_rdc_only():
    options = deepcopy(DEFAULT_OPTIONS)
    options["rez_de_chaussee_probability"] = 1.0
    calls = []

    def rdc_ok(candidate, main_width):
        calls.append((candidate, main_width))
        return candidate >= 800  # only 3 columns (~800 px) fit at 2680 px

    for seed in range(30):
        calls.clear()
        draws = draw_layout(random.Random(seed), options, column_ok=always, rdc_column_ok=rdc_ok, **PAGE)
        main = draws["zones"][0]["columns"][0]
        assert calls and {m for _, m in calls} == {main[1] - main[0]}
        assert len(draws["zones"][1]["columns"]) == 3


def test_rdc_callback_does_not_change_draws_when_it_accepts_like_column_ok():
    options = deepcopy(DEFAULT_OPTIONS)
    options["rez_de_chaussee_probability"] = 1.0
    for seed in range(30):
        plain = draw_layout(random.Random(seed), options, column_ok=always, **PAGE)
        with_rdc = draw_layout(random.Random(seed), options, column_ok=always,
                               rdc_column_ok=lambda c, m: True, **PAGE)
        assert plain == with_rdc


def test_without_rdc_callback_column_ok_filters_the_rdc():
    options = deepcopy(DEFAULT_OPTIONS)
    options.update(rez_de_chaussee_probability=1.0, main_columns={"choice": [6], "weights": [1]})
    draws = draw_layout(random.Random(0), options, column_ok=lambda w: w < 500 or w >= 800, **PAGE)
    assert len(draws["zones"][1]["columns"]) == 3


def test_rdc_callback_refusing_everything_is_a_controlled_error():
    options = deepcopy(DEFAULT_OPTIONS)
    options["rez_de_chaussee_probability"] = 1.0
    with pytest.raises(LayoutError, match="rez_de_chaussee_columns"):
        draw_layout(random.Random(0), options, column_ok=always, rdc_column_ok=lambda c, m: False, **PAGE)
