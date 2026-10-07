"""A1 structural report: pinned calibrer engine, no I/O while measuring, hand-written expectations.

Expectations (tests/fixtures/realism) were frozen with their SHA-256 before realism.py existed
(SPEC-A1 r2 + r2.1). Any difference with the computation must be explained, not silently corrected.
"""

import builtins
import hashlib
import io
import json
import math
import os
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from mille_feuilles import realism
from mille_feuilles.io import ROOT
from mille_feuilles.realism import (
    STATUSES,
    RealismError,
    aggregate,
    build_report,
    canonical_to_pg,
    compare,
    load_engine,
    load_reference,
    measure_pages,
    merge_measures,
)
from mille_feuilles.validation import validate_page

REPO = ROOT
CALIBRER = REPO / "tools/cadrage/calibrer.py"
CALIBRATION = REPO / "tools/cadrage/sortie/calibration.json"
FIXTURE_1 = REPO / "tests/fixtures/newseye/fixture-1-order.json"
EXPECTED = Path(__file__).resolve().parent / "fixtures/realism"
FROZEN = {"expected-fixture-1.json": "c69c19bf613a27d7313c893fbc20475cb5cd614e857c92ed3d0222d9cc3a0ffd",
          "expected-micro.json": "0088db05c2b419e8d91c6c6d267dded9b9162715cf6fa45046311a8c085c05a4"}


def expected(name):
    data = (EXPECTED / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == FROZEN[name], "frozen expectation altered"
    return json.loads(data)


def close(a, b, tol=1e-9):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(close(a[k], b[k], tol) for k in a)
    return math.isclose(a, b, abs_tol=tol)


@pytest.fixture(scope="module")
def engine():
    return load_engine(CALIBRER)


@pytest.fixture
def page():
    return json.loads(FIXTURE_1.read_text(encoding="utf-8"))


# --- pinned loader (r2.1) -------------------------------------------------------------


def test_engine_is_a_fresh_unregistered_module_with_pure_functions(engine):
    assert engine.__name__ == realism.ENGINE_MODULE != "__main__"
    assert realism.ENGINE_MODULE not in sys.modules
    assert load_engine(CALIBRER) is not engine
    for name in ("mesurer", "q", "type_blocks", "columns", "baseline_y", "area", "bbox"):
        assert callable(getattr(engine, name))


def test_altered_calibrer_is_refused_before_compilation(tmp_path, monkeypatch):
    altered = tmp_path / "calibrer.py"
    data = bytearray(CALIBRER.read_bytes())
    data[-2] = ord(" ") if data[-2] != ord(" ") else ord("\t")
    altered.write_bytes(bytes(data))
    monkeypatch.setattr(builtins, "compile", lambda *a, **k: pytest.fail("compiled despite bad SHA"))
    with pytest.raises(RealismError) as caught:
        load_engine(altered)
    assert caught.value.code == "sha_calibrer"


def test_loader_reads_the_file_once_and_never_again(tmp_path, monkeypatch):
    copy = tmp_path / "calibrer.py"
    copy.write_bytes(CALIBRER.read_bytes())
    reads, inside = [], []
    original = Path.read_bytes

    def counted(self):
        if Path(self) == copy:
            reads.append(1)
            if len(reads) > 1:
                raise AssertionError("calibrer.py re-read")
            inside.append(1)  # Path.read_bytes opens the file itself: allowed only here, once
            try:
                return original(self)
            finally:
                inside.pop()
        return original(self)

    def forbid(*args, **kwargs):
        if not inside and any(str(copy) in str(a) for a in args):
            raise AssertionError("calibrer.py reopened")
        return real_open(*args, **kwargs)

    real_open = builtins.open
    monkeypatch.setattr(Path, "read_bytes", counted)
    monkeypatch.setattr(builtins, "open", forbid)
    monkeypatch.setattr(io, "open", forbid)
    loaded = load_engine(copy)
    assert reads == [1] and callable(loaded.mesurer)
    assert not (tmp_path / "__pycache__").exists() and not list(tmp_path.rglob("*.pyc"))


# --- reference ------------------------------------------------------------------------


def test_reference_is_pinned_and_declares_grouped_train_dev():
    reference = load_reference(CALIBRATION, "as:XIXe")
    assert reference["pages"] == 65 and reference["pages_by_split"] == {"dev": 12, "train": 53}
    assert sum(reference["columns_by_split"]["train"].values()) == 53
    assert "regroupent train et dev" in reference["note"]


def test_reference_refusals(tmp_path):
    with pytest.raises(RealismError) as caught:
        load_reference(CALIBRATION, "as:XVIIIe")
    assert caught.value.code == "cohort"
    altered = tmp_path / "calibration.json"
    altered.write_bytes(CALIBRATION.read_bytes() + b" ")
    with pytest.raises(RealismError) as caught:
        load_reference(altered)
    assert caught.value.code == "calibration"


# --- hand-written expectations ----------------------------------------------------------


@pytest.mark.parametrize("variant, include", [("with_template", True), ("without_template", False)])
def test_fixture_1_matches_hand_computed_values(engine, page, variant, include):
    want = expected("expected-fixture-1.json")[variant]
    got = measure_pages([page], engine, include_template=include)
    for name, value in want["values"].items():
        assert name in got["values"] and close(got["values"][name], value), name
    for name, value in want["counts"].items():
        assert close(got["counts"][name], value), name
    for name in want.get("absent", []):
        assert name not in got["values"], name


def test_micro_q_columns_baseline_and_rotation(engine):
    micro = expected("expected-micro.json")
    for case in micro["q"]:
        assert close(engine.q(case["input"]), case["expected"])
    for case in micro["columns"]:
        assert close(engine.columns([tuple(i) for i in case["items"]], case["W"]), case["expected"]), case["case"]
    for case in micro["baseline_y"]:
        assert engine.baseline_y(case["line"]) == case["expected"]
    rotation = micro["rotation"]
    t = math.radians(0.35)
    rotated = [(x * math.cos(t) - y * math.sin(t), x * math.sin(t) + y * math.cos(t)) for x, y in rotation["native"]]
    want = rotation["expected"]
    assert close(engine.area(rotation["native"]), want["area_native"], want["area_tolerance"])
    assert close(engine.area(rotated), want["area_rotated"], want["area_tolerance"])
    x0, y0, x1, y1 = engine.bbox(rotated)
    # Documented difference: hand value 19.83224845 vs computed 19.83224848 (3e-8, manual trigonometric
    # rounding), within the declared tolerance; the expectation is kept as frozen.
    assert close(y1 - y0, want["aabb_height_rotated"], want["aabb_tolerance"])
    assert close(x1 - x0, want["aabb_width_rotated"], want["aabb_tolerance"])


def test_micro_pages(engine):
    for case in expected("expected-micro.json")["pages"]:
        values = defaultdict(lambda: defaultdict(list))
        counts = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        engine.mesurer(case["pg"], "mf", None, values, counts, "")
        got = values["mf"]
        for name, value in case["expected_values"].items():
            assert name in got and close(got[name], value), (case["case"], name)
        for name in case.get("expected_absent", []):
            assert name not in got


# --- no I/O while measuring --------------------------------------------------------------


def _trap(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("I/O during measurement")

    for owner, name in ((builtins, "open"), (io, "open"), (os, "open")):
        monkeypatch.setattr(owner, name, refuse)
    for name in ("open", "read_bytes", "read_text", "exists"):
        monkeypatch.setattr(Path, name, refuse)


def test_measurement_and_aggregation_perform_no_io(engine, page, monkeypatch):
    pages = [page, deepcopy(page)]
    _trap(monkeypatch)
    measures = measure_pages(pages, engine)
    stats = aggregate(measures, engine)
    assert stats["colonnes"]["n"] == 2


def test_the_io_trap_actually_fires(monkeypatch):
    _trap(monkeypatch)
    with pytest.raises(AssertionError, match="I/O during measurement"):
        Path("x").read_text()
    with pytest.raises(AssertionError, match="I/O during measurement"):
        open("x")


# --- adapter and refusals ------------------------------------------------------------------


def test_adapter_structure_matches_parse_page_shape(page):
    pg = canonical_to_pg(page)
    assert set(pg) == {"width", "height", "regions", "order", "groups", "printspace"}
    kinds = {r["id"]: (r["kind"], r["struct"]) for r in pg["regions"]}
    assert kinds["p_b0000"] == ("TextRegion", "heading") and kinds["p_b0002"] == ("TextRegion", None)
    assert kinds["p_b0003__advert"] == ("AdvertRegion", None) and kinds["p_b0005"] == ("SeparatorRegion", None)
    assert pg["order"] == page["reading_order"]["block_ids"] and pg["printspace"] is None
    line = next(r for r in pg["regions"] if r["id"] == "p_b0002")["lines"][0]
    assert line["article"] == "p_a0001" and line["text"] == "Le conseil a"


def test_table_block_is_refused(page):
    page["blocks"][2]["category"] = "tableau"
    with pytest.raises(RealismError) as caught:
        canonical_to_pg(page)
    assert caught.value.code == "table_block"


def test_missing_template_key_makes_the_sensitivity_variant_nd(engine, page):
    del page["provenance"]["extensions"]["mf:template_article_ids"]
    assert canonical_to_pg(page, include_template=False) is None
    measures = measure_pages([page], engine, include_template=False)
    assert measures["pages"] == [] and measures["excluded"][0]["reason"] == "template_identification_unavailable"
    assert canonical_to_pg(page, include_template=True) is not None


@pytest.mark.parametrize("target, polygon", [
    ("p_b0004", [[0, 40], [5, 40], [5, 75], [140, 75], [140, 100], [0, 100]]),
    ("p_b0002", [[10, 70], [120, 70], [120, 120], [320, 120],
                 [320, 70], [330, 70], [330, 125], [10, 125]]),
])
@pytest.mark.parametrize("category", ["texte", "autre"])
def test_disjoint_advert_polygon_cannot_silently_retype_text(
    engine, page, monkeypatch, target, polygon, category
):
    blocks = {b["id"]: b for b in page["blocks"]}
    blocks["p_b0003"]["polygon"] = polygon
    blocks[target]["category"] = category
    assert validate_page(page) == []
    assert Polygon(polygon).intersection(Polygon(blocks[target]["polygon"])).area == 0
    typed = {b["id"]: b["category"] for b in engine.type_blocks(canonical_to_pg(page))}
    assert typed[target] == "annonce"  # Real D-231 behavior, not a mocked category change.
    monkeypatch.setattr(engine, "mesurer", lambda *a, **k: pytest.fail("measured despite retyping"))
    for include in (True, False):
        with pytest.raises(RealismError) as caught:
            measure_pages([page], engine, include_template=include)
        assert caught.value.code == "category_retyping"
        assert f"page {page['page_id']}" in str(caught.value)
        assert f"{target}: {category} → annonce" in str(caught.value)


def test_illustration_suppressed_by_d231_is_refused_before_measurement(engine, page, monkeypatch):
    body = next(b for b in page["blocks"] if b["id"] == "p_b0002")
    page["blocks"].append({"id": "p_graphic", "category": "illustration",
                           "polygon": deepcopy(body["polygon"]), "article_id": None, "line_ids": []})
    page["reading_order"]["unordered_block_ids"].append("p_graphic")
    assert validate_page(page) == []
    typed_ids = {b["id"] for b in engine.type_blocks(canonical_to_pg(page))}
    assert "p_graphic" not in typed_ids
    monkeypatch.setattr(engine, "mesurer", lambda *a, **k: pytest.fail("measured despite disappearance"))
    with pytest.raises(RealismError) as caught:
        measure_pages([page], engine)
    assert caught.value.code == "category_retyping"
    assert "p_graphic: illustration → absent" in str(caught.value)


@pytest.mark.parametrize("cohort, pages", [("bnf:XIXe", 16), ("read", 44), ("kb", 1017)])
def test_single_split_reference_does_not_claim_a_train_dev_merge(cohort, pages):
    reference = load_reference(CALIBRATION, cohort)
    assert reference["pages_by_split"] == {"train": pages}
    assert "uniquement sur le split train" in reference["note"]
    assert "dev" not in reference["note"]


def test_mixed_reference_declares_both_splits_without_splitting_quantiles():
    reference = load_reference(CALIBRATION, "as:XIXe")
    assert reference["pages_by_split"] == {"train": 53, "dev": 12}
    assert "train" in reference["note"] and "dev" in reference["note"]
    assert "regroupent" in reference["note"]
    assert "seul l'histogramme des colonnes est séparable" in reference["note"]


# --- aggregation and comparison --------------------------------------------------------------


def test_aggregate_uses_q_for_lists_and_valeur_part_for_counts(engine):
    stats = aggregate({"values": {"x": [0, 10]}, "counts": {"blocs_nombre": {"titre": 3.0, "texte": 1.0}}}, engine)
    assert stats["x"]["p10"] == 1.0 and stats["x"]["p90"] == 9.0
    assert stats["blocs_nombre"] == {"titre": {"valeur": 3.0, "part": 0.75}, "texte": {"valeur": 1.0, "part": 0.25}}
    assert list(stats["blocs_nombre"]) == ["titre", "texte"]


def q_like(p10, p50, p90, n=10):
    return {"n": n, "p10": p10, "p50": p50, "p90": p90}


@pytest.mark.parametrize(
    "mf_p50, position", [(1.0, "p10–p90"), (3.0, "p10–p90"), (0.999, "< p10"), (3.001, "> p90"), (2.0, "p10–p90")]
)
def test_position_is_descriptive_with_inclusive_bounds(mf_p50, position):
    result = compare({"colonnes": q_like(0, mf_p50, 9)}, {"colonnes": q_like(1.0, 2.0, 3.0)})
    assert result["colonnes"]["position"] == position and result["colonnes"]["status"] == "C"


def test_non_compared_cases():
    real = {"interligne_px_med_page": q_like(1, 2, 3), "annonce_avec_titre": q_like(0, 0, 1),
            "colonnes": q_like(1, 2, 3), "printspace_haut_rel_H": q_like(0, 0.1, 0.2),
            "articles_par_page": q_like(18, 33, 57)}
    mf = {"interligne_px_med_page": q_like(1, 2, 3), "annonce_avec_titre": q_like(0, 0, 0),
          "colonnes": {"n": 1, "p50": 2}}
    result = compare(mf, real)
    px = result["interligne_px_med_page"]
    assert px["status"] == "A" and px["comparison_allowed"] is False and px["position"] == "non comparé"
    assert result["annonce_avec_titre"]["status"] == "NC" and result["annonce_avec_titre"]["position"] == "non comparé"
    assert result["colonnes"]["position"].startswith("non comparé (n = 1")
    assert result["colonnes"]["comparison_allowed"] is False
    assert result["printspace_haut_rel_H"]["status"] == "ND"  # absent on the MF side: absence ≠ zero
    assert result["blocs_nombre"]["status"] == "ND"  # absent on both sides
    missing = result["articles_par_page"]  # effective ND, definition status kept
    assert missing["status"] == "ND" and missing["definition_status"] == "A"


def test_only_four_public_statuses_and_every_entry_has_a_sample_unit():
    stats = {"colonne_largeur_rel_W": q_like(0.1, 0.2, 0.3), "article_lignes": q_like(1, 5, 9),
             "titre_ligne_sur_corps_texte": q_like(1, 2, 3), "ordre_transitions": {"x": {"valeur": 1, "part": 1.0}}}
    result = compare(stats, stats)
    assert {entry["status"] for entry in result.values()} <= set(STATUSES) == {"C", "A", "NC", "ND"}
    assert {entry["definition_status"] for entry in result.values()} <= set(STATUSES)
    assert all(entry["sample_unit"] for entry in result.values())
    assert result["colonne_largeur_rel_W"]["sample_unit"] == "colonne"
    assert result["gouttiere_rel_W"]["sample_unit"] == "gouttière"
    assert result["article_lignes"]["sample_unit"] == "article"
    assert result["titre_ligne_sur_corps_texte"]["sample_unit"] == "ligne de titre"
    assert result["filet_vertical_longueur_rel_H"]["sample_unit"] == "filet vertical"
    assert result["colonnes"]["sample_unit"] == "page"
    counts = result["ordre_transitions"]
    assert counts["kind"] == "counts" and counts["sample_unit"] == "compte de transitions d'ordre"
    assert result["colonnes"]["kind"] == "distribution"


def test_has_autre_counts_only_blocks_kept_in_the_variant(engine, page):
    template = page["provenance"]["extensions"]["mf:template_article_ids"]
    banner = next(b for b in page["blocks"] if b.get("article_id") in template)
    banner["category"] = "autre"  # the only "autre" block belongs to the template
    assert measure_pages([page], engine, include_template=True)["has_autre"] is True
    assert measure_pages([page], engine, include_template=False)["has_autre"] is False
    outside = next(b for b in page["blocks"] if b["category"] == "texte")
    outside["category"] = "autre"
    assert measure_pages([page], engine, include_template=False)["has_autre"] is True


def test_page_by_page_merge_equals_one_batch(engine, page):
    other = deepcopy(page)
    del other["provenance"]["extensions"]["mf:template_article_ids"]
    pages = [page, other, deepcopy(page)]
    for include in (True, False):
        batch = measure_pages(pages, engine, include_template=include)
        merged = merge_measures([measure_pages([p], engine, include_template=include) for p in pages])
        assert merged["values"] == batch["values"] and merged["counts"] == batch["counts"]
        assert merged["pages"] == batch["pages"] and merged["excluded"] == batch["excluded"]
        assert aggregate(merged, engine) == aggregate(batch, engine)


def test_counts_are_reported_as_parts_without_quantiles():
    real = {"ordre_transitions": {"dessous_meme_colonne": {"valeur": 5, "part": 0.5}}}
    mf = {"ordre_transitions": {"dessous_meme_colonne": {"valeur": 3, "part": 0.75}}}
    assert compare(mf, real)["ordre_transitions"]["position"].startswith("parts rapportées")


def test_autre_propagates_approximation_to_text_influenced_metrics():
    stats = {"caracteres_par_ligne_med_page": q_like(40, 42, 48), "filets_par_page": q_like(1, 2, 3)}
    result = compare(stats, stats, has_autre=True)
    assert result["caracteres_par_ligne_med_page"]["status"] == "A"
    assert result["filets_par_page"]["status"] == "C"


def test_report_has_both_variants_with_their_roles(engine, page):
    reference = load_reference(CALIBRATION, "as:XIXe")
    report = build_report([page], engine, reference)
    assert report["variants"]["avec_gabarit"]["role"] == "protocole historique"
    assert report["variants"]["sans_gabarit"]["role"] == "analyse de sensibilité au bandeau"
    assert "aucun verdict" in report["scope"]
    comparison = report["variants"]["avec_gabarit"]["comparison"]
    assert comparison["annonce_avec_titre"]["status"] == "NC"
    assert comparison["page_largeur_cm"]["status"] == "ND"
    assert report["variants"]["sans_gabarit"]["cohort_status"] == "complete"


def test_partial_template_identification_neutralises_the_sensitivity_cohort(engine, page):
    other = deepcopy(page)
    other["page_id"] = "sans_cle"
    del other["provenance"]["extensions"]["mf:template_article_ids"]
    report = build_report([page, other], engine, load_reference(CALIBRATION, "as:XIXe"))
    sensitivity = report["variants"]["sans_gabarit"]
    assert sensitivity["cohort_status"] == "ND" and sensitivity["comparison"] is None
    assert "1 page(s) sur 2" in sensitivity["cohort_reason"]
    assert [p["page_id"] for p in sensitivity["pages"]] == [page["page_id"]]
    assert sensitivity["excluded"] == [{"page_id": "sans_cle", "reason": "template_identification_unavailable"}]
    assert sensitivity["partial_observations"]["colonnes"]["n"] == 1
    assert report["variants"]["avec_gabarit"]["cohort_status"] == "complete"
