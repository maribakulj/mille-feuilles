"""Original canonical-only fixtures; no PNG, asset, corpus or render is needed.

The real canonical validator and pinned measurement engine run. The miniature
native manifest is structurally valid but its images/assets deliberately do not
exist: success must never imply a full dataset audit. Only Git state is fixed
for deterministic tests during parallel development. Disk capacity is simulated
only for these bounded unit fixtures after checking their real <5 MB allowance;
the production CLI and its 500 MB reserve are never changed.
"""
import gc
import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from mille_feuilles import structure_report as reports
from mille_feuilles import validation
from mille_feuilles import realism

FIXTURE = reports.ROOT / "tests/fixtures/newseye/fixture-1-order.json"


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def source_fixture(root, ids=("p", "q"), *, version="0.3.0", change=None):
    root.mkdir()
    (root / "pages").mkdir()
    entries = []
    for identity in ids:
        raw = FIXTURE.read_text().replace('"p"', f'"{identity}"')
        raw = raw.replace('"p_', f'"{identity}_').replace("images/p.png", f"images/{identity}.png")
        page = json.loads(raw)
        page["schema_version"] = version
        if version == "0.2.0":
            for span in page["provenance"]["text_spans"]:
                span.pop("article_id")
                span.pop("block_ids")
        if change:
            change(identity, page)
        data = encode(page)
        (root / f"pages/{identity}.json").write_bytes(data)
        entries.append({"id": identity, "path": f"pages/{identity}.json", "sha256": digest(data),
                        "source_group_ids": ["original_fixture"]})
    manifest = {"schema_version": version, "dataset_id": "original_fixture",
                "profile": "fr_press_19c_columns_4_6",
                "generator": {"commit": "a" * 40, "dirty": False, "environment_path": "environment.json",
                              "environment_sha256": "0" * 64},
                "config": {"path": "config.json", "sha256": "0" * 64},
                "rng": {"algorithm": "fixture", "version": "1", "seed": 0},
                "assets": {"path": "assets.json", "sha256": "0" * 64},
                "calibration": {"protocol_path": "calibration.json", "protocol_sha256": "0" * 64,
                                "source_partitions": ["train"],
                                "files_read": {"path": "files-read.json", "sha256": "0" * 64}},
                "pages": entries,
                "artifacts": [{"path": e["path"], "sha256": e["sha256"], "role": "page"} for e in entries]}
    (root / "manifest.json").write_bytes(encode(manifest))
    return root


def change_page(root, identity, mutate, *, update_hash=True):
    path = root / f"pages/{identity}.json"
    page = read(path)
    mutate(page)
    data = encode(page)
    path.write_bytes(data)
    if update_hash:
        manifest = read(root / "manifest.json")
        for row in manifest["pages"] + manifest["artifacts"]:
            if row["path"] == f"pages/{identity}.json":
                row["sha256"] = digest(data)
        (root / "manifest.json").write_bytes(encode(manifest))


@pytest.fixture(scope="module", autouse=True)
def tiny_fixture_space(tmp_path_factory):
    # Complete fixture tree measured below 5 MB; no production guard is bypassed.
    if shutil.disk_usage(tmp_path_factory.getbasetemp()).free < 5_000_000:
        pytest.skip("Less than the bounded 5 MB unit-fixture allowance remains")


@pytest.fixture(autouse=True)
def stable_git_and_capacity(monkeypatch):
    monkeypatch.setattr(reports, "git_state", lambda: ("a" * 40, False))
    monkeypatch.setattr(reports.shutil, "disk_usage", lambda _: SimpleNamespace(free=2_000_000_000))


def test_two_files_true_measurements_and_source_order(tmp_path):
    source = source_fixture(tmp_path / "source")
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*.json")}
    result = reports.build_report(source, tmp_path / "report", page_ids=["q", "p"])
    assert result["status"] == "pass" and result["selected_page_ids"] == ["p", "q"]
    output = tmp_path / "report"
    assert sorted(p.name for p in output.iterdir()) == ["report.json", "report.sha256"]
    data = (output / "report.json").read_bytes()
    assert (output / "report.sha256").read_text() == f"{digest(data)}  report.json\n"
    report = json.loads(data)
    assert result["report_sha256"] == digest(data)
    assert report["scope"]["source_dataset_validation"] == "not_performed"
    assert report["scope"]["realism_verdict"] == "not_evaluated"
    assert report["reference"]["pages"] == 65
    assert report["reference"]["pages_by_split"] == {"dev": 12, "train": 53}
    assert report["inputs"]["calibrer"]["sha256"] == realism.CALIBRER_SHA256
    assert report["inputs"]["calibration"]["sha256"] == realism.CALIBRATION_SHA256
    assert report["inputs"]["source"]["manifest"]["sha256"] == digest(before[Path("manifest.json")])
    for variant in report["variants"].values():
        assert variant["cohort_status"] == "complete"
        assert variant["stats"]["colonnes"]["n"] == 2
        assert variant["partial_stats"] is None
        assert variant["comparison"]["annonce_avec_titre"]["status"] == "NC"
        assert not variant["comparison"]["ligne_hauteur_px_med_page"]["comparison_allowed"]
        assert "n" not in variant["comparison"]["blocs_nombre"]["mf"]
    assert report["selection"]["pages"][0]["angle_degrees"] is None
    assert report["selection"]["pages"][0]["oversampling"] is None
    assert all((source / relative).read_bytes() == data for relative, data in before.items())
    assert not (source / "images").exists()


def test_no_unselected_page_image_asset_export_or_dataset_validation_read(tmp_path, monkeypatch):
    source = source_fixture(tmp_path / "source")
    (source / "pages/q.json").write_text("malformed and deliberately unselected")
    original = Path.open
    opened = []

    def guarded(self, mode="r", *args, **kwargs):
        path = self.resolve()
        if path.is_relative_to(source):
            relative = path.relative_to(source).as_posix()
            assert relative in {"manifest.json", "pages/p.json"}, relative
            assert not any(flag in mode for flag in "wax+"), "source written"
            opened.append(relative)
        return original(self, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    monkeypatch.setattr(validation, "validate_dataset", lambda *a, **k: pytest.fail("full dataset validator invoked"))
    result = reports.build_report(source, tmp_path / "report", page_ids=["p"])
    assert result["status"] == "pass"
    assert set(opened) == {"manifest.json", "pages/p.json"}


def test_page_by_page_does_not_hold_previous_canonical(tmp_path, monkeypatch):
    source = source_fixture(tmp_path / "source", ("p", "q", "r"))
    original = realism.measure_pages
    seen = []

    def measured(pages, engine, *, include_template=True):
        assert len(pages) == 1
        page = pages[0]
        if page["page_id"] == "q":
            gc.collect()
            assert not any(isinstance(value, dict) and value.get("page_id") == "p"
                           and "reading_order" in value for value in gc.get_objects())
        seen.append((page["page_id"], include_template))
        return original(pages, engine, include_template=include_template)
    monkeypatch.setattr(realism, "measure_pages", measured)
    reports.build_report(source, tmp_path / "report", all_pages=True)
    assert seen == [(identity, include) for identity in ("p", "q", "r") for include in (True, False)]


@pytest.mark.parametrize("reference", ["as", "as:XIXe", "as:XXe", "bnf", "bnf:XIXe", "bnf:XXe", "kb", "read"])
def test_reference_uses_only_one_existing_aggregate(tmp_path, reference):
    source = source_fixture(tmp_path / "source", ("p",))
    reports.build_report(source, tmp_path / "report", all_pages=True, reference=reference)
    report = read(tmp_path / "report/report.json")
    assert report["reference"]["cohort"] == reference
    assert sum(report["reference"]["pages_by_split"].values()) == report["reference"]["pages"]
    if reference.startswith("bnf") or reference in {"read", "kb"}:
        assert report["variants"]["avec_gabarit"]["comparison"]["articles_par_page"]["status"] == "ND"


def test_missing_template_metadata_neutralizes_entire_sensitivity_cohort(tmp_path):
    def alter(identity, page):
        if identity == "q":
            del page["provenance"]["extensions"]["mf:template_article_ids"]
    source = source_fixture(tmp_path / "source", version="0.2.0", change=alter)
    reports.build_report(source, tmp_path / "report", all_pages=True)
    variant = read(tmp_path / "report/report.json")["variants"]["sans_gabarit"]
    assert variant["cohort_status"] == "ND"
    assert variant["stats"] is None and variant["comparison"] is None
    assert [row["page_id"] for row in variant["per_page"]] == ["p"]
    assert variant["partial_stats"]["colonnes"]["n"] == 1
    assert variant["excluded"] == [{"page_id": "q", "reason": "template_identification_unavailable"}]
    assert variant["per_page"][0]["removed_article_ids"] == ["p_a0000"]
    assert variant["per_page"][0]["removed_block_ids"] == ["p_b0000"]


def test_empty_template_ids_is_known_no_removal(tmp_path):
    def alter(identity, page):
        page["provenance"]["extensions"]["mf:template_article_ids"] = []
    source = source_fixture(tmp_path / "source", ("p",), version="0.2.0", change=alter)
    reports.build_report(source, tmp_path / "report", all_pages=True)
    report = read(tmp_path / "report/report.json")
    variant = report["variants"]["sans_gabarit"]
    assert variant["cohort_status"] == "complete" and variant["excluded"] == []
    assert variant["per_page"][0]["removed_block_ids"] == []
    assert variant["stats"] == report["variants"]["avec_gabarit"]["stats"]


@pytest.mark.parametrize("selection", [dict(), {"page_ids": []}, {"page_ids": ["p", "p"]},
                                       {"page_ids": ["unknown"]}, {"page_ids": "p"},
                                       {"page_ids": ["p"], "all_pages": True}, {"all_pages": 1}])
def test_selection_required_and_unambiguous(tmp_path, selection):
    source = source_fixture(tmp_path / "source")
    with pytest.raises(ValueError):
        reports.build_report(source, tmp_path / "report", **selection)
    assert not (tmp_path / "report").exists()


@pytest.mark.parametrize("kind", ["existing", "nested", "alias", "dangling", "same"])
def test_new_disjoint_destination(tmp_path, kind):
    source = source_fixture(tmp_path / "source")
    target = tmp_path / "report"
    if kind == "existing":
        target.mkdir()
    elif kind == "nested":
        target = source / "report"
    elif kind == "alias":
        (tmp_path / "alias").symlink_to(source, target_is_directory=True)
        target = tmp_path / "alias/report"
    elif kind == "dangling":
        target.symlink_to(tmp_path / "absent")
    else:
        target = source
    with pytest.raises(ValueError):
        reports.build_report(source, target, all_pages=True)
    if kind in {"nested", "alias"}:
        assert not target.exists()


@pytest.mark.parametrize("kind", ["sha", "id", "image_path", "profile", "version", "geometry", "path", "traversal"])
def test_selected_canonical_binding_errors_before_output(tmp_path, kind):
    source = source_fixture(tmp_path / "source", ("p",))
    if kind in {"path", "traversal"}:
        manifest = read(source / "manifest.json")
        manifest["pages"][0]["path"] = "../p.json" if kind == "traversal" else "pages/other.json"
        (source / "manifest.json").write_bytes(encode(manifest))
    else:
        def mutate(page):
            if kind == "sha":
                page["image"]["dpi"] += 1
            elif kind == "id":
                page["page_id"] = "different"
            elif kind == "image_path":
                page["image"]["path"] = "images/different.png"
            elif kind == "profile":
                page["profile"] = "fr_press_19c_columns_4_6_measured"
            elif kind == "version":
                page["schema_version"] = "0.2.0"
                for span in page["provenance"]["text_spans"]:
                    span.pop("article_id")
                    span.pop("block_ids")
            else:
                page["words"][0]["polygon"] = [[1, 1], [1, 1], [1, 1]]
        change_page(source, "p", mutate, update_hash=kind != "sha")
    with pytest.raises(ValueError):
        reports.build_report(source, tmp_path / "report", all_pages=True)
    assert not (tmp_path / "report").exists()


@pytest.mark.parametrize("kind", ["calibrer", "calibration"])
def test_pinned_files_altered_refused_before_engine(tmp_path, monkeypatch, kind):
    source = source_fixture(tmp_path / "source", ("p",))
    original = reports.CALIBRER_PATH if kind == "calibrer" else reports.CALIBRATION_PATH
    altered = tmp_path / original.name
    altered.write_bytes(original.read_bytes() + b"\n")
    monkeypatch.setattr(reports, "CALIBRER_PATH" if kind == "calibrer" else "CALIBRATION_PATH", altered)
    monkeypatch.setattr(realism, "load_engine", lambda *a, **k: pytest.fail("engine loaded after bad SHA"))
    with pytest.raises(ValueError, match="Pinned"):
        reports.build_report(source, tmp_path / "report", all_pages=True)
    assert not (tmp_path / "report").exists()


@pytest.mark.parametrize("kind", ["pages", "canonical_bytes", "output_bytes", "disk"])
def test_execution_budgets_are_refusals(tmp_path, monkeypatch, kind):
    source = source_fixture(tmp_path / "source")
    if kind == "pages":
        monkeypatch.setattr(reports, "MAX_PAGES", 1)
    elif kind == "canonical_bytes":
        monkeypatch.setattr(reports, "MAX_CANONICAL_BYTES", 100)
    elif kind == "output_bytes":
        # Enough for pinned inputs, too little after normal report encoding.
        original = reports._encoded
        monkeypatch.setattr(reports, "_encoded", lambda value: original(value) + b" " * reports.MAX_OUTPUT_BYTES)
    else:
        monkeypatch.setattr(reports.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(ValueError):
        reports.build_report(source, tmp_path / "report", all_pages=True)
    assert not (tmp_path / "report").exists()


@pytest.mark.parametrize("code", ["table_block", "category_retyping"])
def test_measurement_refusals_propagate_before_creation(tmp_path, monkeypatch, code):
    source = source_fixture(tmp_path / "source", ("p",))

    def refused(*args, **kwargs):
        raise realism.RealismError(code, "controlled measurement refusal")
    monkeypatch.setattr(realism, "measure_pages", refused)
    with pytest.raises(realism.RealismError) as caught:
        reports.build_report(source, tmp_path / "report", all_pages=True)
    assert caught.value.code == code
    assert not (tmp_path / "report").exists()


def test_source_mutation_during_measurement_refused(tmp_path, monkeypatch):
    source = source_fixture(tmp_path / "source", ("p",))
    original = realism.measure_pages

    def measure(pages, engine, *, include_template=True):
        result = original(pages, engine, include_template=include_template)
        with (source / "pages/p.json").open("ab") as stream:
            stream.write(b" ")
        return result
    monkeypatch.setattr(realism, "measure_pages", measure)
    with pytest.raises(ValueError, match="Selected source changed"):
        reports.build_report(source, tmp_path / "report", all_pages=True)
    assert not (tmp_path / "report").exists()


def test_failed_write_preserves_partial_output_and_source(tmp_path, monkeypatch):
    source = source_fixture(tmp_path / "source", ("p",))
    output = tmp_path / "report"
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*.json")}
    original = Path.open

    def failed(self, mode="r", *args, **kwargs):
        if self == output / "report.sha256" and mode == "xb":
            raise OSError("simulated digest write failure")
        return original(self, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", failed)
    with pytest.raises(OSError, match="simulated digest"):
        reports.build_report(source, output, all_pages=True)
    assert (output / "report.json").is_file()
    assert all((source / relative).read_bytes() == data for relative, data in before.items())


@pytest.mark.parametrize("value", [True, False, 10**400, float("inf"), float("nan"), "1", []])
def test_unknown_numeric_metadata_is_a_controlled_refusal(value):
    with pytest.raises(ValueError, match="Invalid declared metadata"):
        reports._number(value, "angle_degrees")


def test_huge_parameter_is_refused_before_measurement(tmp_path, monkeypatch):
    source = source_fixture(tmp_path / "source", ("p",))
    change_page(source, "p", lambda page: page["provenance"]["parameters"].update(angle_degrees=10**400))
    monkeypatch.setattr(realism, "measure_pages", lambda *a, **k: pytest.fail("invalid metadata measured"))
    with pytest.raises(ValueError, match="non-finite"):
        reports.build_report(source, tmp_path / "report", all_pages=True)
    assert not (tmp_path / "report").exists()


def test_real_table_refusal_before_creation(tmp_path):
    source = source_fixture(tmp_path / "source", ("p",))
    change_page(source, "p", lambda page: page["blocks"][4].update(category="tableau"))
    assert validation.validate_page(read(source / "pages/p.json")) == []
    with pytest.raises(realism.RealismError) as caught:
        reports.build_report(source, tmp_path / "report", all_pages=True)
    assert caught.value.code == "table_block"
    assert not (tmp_path / "report").exists()


def test_valid_canonical_profile_must_match_manifest(tmp_path):
    source = source_fixture(tmp_path / "source", ("p",))
    manifest = read(source / "manifest.json")
    manifest["profile"] = "fr_press_19c_columns_4_6_measured"
    manifest["extensions"] = {"mf:degradation_profile": {
        "path": "provenance/degradation-profile.json", "sha256": "0" * 64,
    }}
    (source / "manifest.json").write_bytes(encode(manifest))
    assert validation.validate_page(read(source / "pages/p.json")) == []
    with pytest.raises(ValueError, match="profile or schema differs"):
        reports.build_report(source, tmp_path / "report", all_pages=True)
    assert not (tmp_path / "report").exists()


def test_engine_file_and_corpus_entrypoints_never_invoked(tmp_path, monkeypatch):
    source = source_fixture(tmp_path / "source", ("p",))
    original = realism.load_engine

    def load(path):
        engine = original(path)
        for name in ("main", "Journal", "parse_page", "image_dpi", "image_dpi_path", "_head"):
            setattr(engine, name, lambda *a, **k: pytest.fail("forbidden calibrer entrypoint called"))
        return engine
    monkeypatch.setattr(realism, "load_engine", load)
    assert reports.build_report(source, tmp_path / "report", all_pages=True)["status"] == "pass"


def test_no_io_inside_measurement_or_aggregation(tmp_path, monkeypatch):
    import builtins
    import io
    import os

    source = source_fixture(tmp_path / "source", ("p",))

    def guarded(function):
        def call(*args, **kwargs):
            def forbidden(*a, **k):
                pytest.fail("I/O during pure measurement/aggregation")
            with pytest.MonkeyPatch.context() as patch:
                for owner, name in ((builtins, "open"), (io, "open"), (os, "open"),
                                    (Path, "open"), (Path, "read_bytes"), (Path, "read_text"), (Path, "exists")):
                    patch.setattr(owner, name, forbidden)
                return function(*args, **kwargs)
        return call
    monkeypatch.setattr(realism, "measure_pages", guarded(realism.measure_pages))
    monkeypatch.setattr(realism, "aggregate", guarded(realism.aggregate))
    assert reports.build_report(source, tmp_path / "report", all_pages=True)["status"] == "pass"


def test_raw_observations_reaggregate_and_reproduce_deterministically(tmp_path):
    source = source_fixture(tmp_path / "source")
    first = reports.build_report(source, tmp_path / "first", all_pages=True)
    second = reports.build_report(source, tmp_path / "second", all_pages=True)
    assert first["report_sha256"] == second["report_sha256"]
    report = read(tmp_path / "first/report.json")
    engine = realism.load_engine(reports.CALIBRER_PATH)
    for variant in report["variants"].values():
        parts = [{**row, "pages": [], "excluded": []} for row in variant["per_page"]]
        merged = realism.merge_measures(parts)
        stats = realism.aggregate(merged, engine)
        assert stats == variant["stats"]
        assert realism.compare(stats, report["reference"]["stats"], has_autre=merged["has_autre"]) == variant["comparison"]


def test_source_changed_during_output_is_reported_and_partial_preserved(tmp_path, monkeypatch):
    source = source_fixture(tmp_path / "source", ("p",))
    original = Path.open
    output = tmp_path / "report"

    def changed(self, mode="r", *args, **kwargs):
        if self == output / "report.sha256" and mode == "xb":
            with original(source / "pages/p.json", "ab") as stream:
                stream.write(b" ")
        return original(self, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", changed)
    with pytest.raises(ValueError, match="Selected source changed"):
        reports.build_report(source, output, all_pages=True)
    assert (output / "report.json").is_file()


def test_code_change_during_measurement_refused_before_output(tmp_path, monkeypatch):
    source = source_fixture(tmp_path / "source", ("p",))
    environment = reports._environment()
    # JSON roundtrip yields a detached snapshot for each capture.
    monkeypatch.setattr(reports, "_environment", lambda: json.loads(json.dumps(environment)))
    original = realism.measure_pages

    def changed(*args, **kwargs):
        measured = original(*args, **kwargs)
        environment["modules"]["realism.py"] = "f" * 64
        return measured
    monkeypatch.setattr(realism, "measure_pages", changed)
    with pytest.raises(ValueError, match="Measurement code or pinned reference changed"):
        reports.build_report(source, tmp_path / "report", all_pages=True)
    assert not (tmp_path / "report").exists()


def test_unknown_or_combined_reference_refused(tmp_path):
    source = source_fixture(tmp_path / "source", ("p",))
    with pytest.raises(realism.RealismError) as caught:
        reports.build_report(source, tmp_path / "report", all_pages=True, reference="as:XIXe+read")
    assert caught.value.code == "cohort"
    assert not (tmp_path / "report").exists()
