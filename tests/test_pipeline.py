"""End-to-end assembly checks with small real images and XML exports."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
from threading import Event, Lock, Thread

import pytest

from mille_feuilles import pipeline
from mille_feuilles.io import ROOT, sha256
from mille_feuilles.render import Config
from mille_feuilles.validation import load_json, validate_dataset


@pytest.fixture(scope="module")
def repeated_lots(tmp_path_factory):
    first = tmp_path_factory.mktemp("pipeline_serial")
    second = tmp_path_factory.mktemp("pipeline_parallel")
    config = Config(width=800, height=1100, columns=4, degradation="mixed", seed=471)
    # Other agents can edit source files while these in-process builds run.
    # Freeze the real initial metadata; loaded renderer/export code and all
    # actual production, validation and serialization remain unmodified.
    snapshot = pipeline.environment()
    git_snapshot = pipeline.git_state()
    progress = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pipeline, "environment", lambda: deepcopy(snapshot))
        patch.setattr(pipeline, "git_state", lambda: git_snapshot)
        serial = pipeline.build_dataset(first, config, count=2, jobs=1, progress=progress.append)
        parallel = pipeline.build_dataset(second, config, count=2, jobs=2)
    return first, second, serial, parallel, progress


def test_two_page_serial_and_parallel_builds_are_bit_identical(repeated_lots):
    first, second, serial, parallel, _ = repeated_lots
    assert serial["status"] == "pass", serial["errors"]
    assert parallel["status"] == "pass", parallel["errors"]
    comparison = pipeline.compare_lots(first, second)
    assert comparison["status"] == "pass", comparison
    assert comparison["files_compared"] > 15
    for folder in ("images", "pages"):
        files = sorted((first / folder).glob("*"))
        assert len(files) == 2
        assert all(
            path.read_bytes() == (second / folder / path.name).read_bytes() for path in files
        )


def test_real_exports_assets_and_qa_are_complete(repeated_lots):
    first, _, report, _, progress = repeated_lots
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["exports"]["status"] == "pass"
    assert checks["export_inventory"]["status"] == "pass"
    assert not any(check["status"] != "pass" for check in report["checks"])
    manifest = load_json(first / "manifest.json")
    indexed = {item["path"] for item in manifest["artifacts"]}
    actual = {str(path.relative_to(first)) for path in first.rglob("*") if path.is_file()}
    assert actual - indexed == {"manifest.json", "qa/report.json"}
    assert "qa/report.json" not in indexed
    assert "qa/statistics.json" in indexed
    for page in manifest["pages"]:
        pid = page["id"]
        assert f"exports/page/{pid}.xml" in indexed
        assert f"exports/alto/{pid}.xml" in indexed
        assert f"exports/reports/{pid}.json" in indexed
        assert f"qa/{pid}.png" in indexed
    assert "exports/coco/instances.json" in indexed
    assert report["statistics"]["pages"] == 2
    assert report["statistics"]["words"] > 100
    assert len(progress) == 3
    assert load_json(first / "qa/report.json")["status"] == "pass"


def test_environment_records_real_software_and_source_fingerprints():
    recorded = pipeline.environment()
    assert recorded["layout_engine"] == "pillow-freetype-basic"
    assert recorded["freetype"]
    assert all(recorded["packages"][name] for name in ("Pillow", "numpy", "lxml", "shapely"))
    for relative in ("src/mille_feuilles/render.py", "schemas/page.schema.json", "uv.lock"):
        assert recorded["sources"][relative] == sha256(ROOT / relative)


@pytest.mark.parametrize("is_directory", [True, False])
def test_nonempty_destination_is_refused_without_touching_user_files(tmp_path, is_directory):
    output = tmp_path / "keep"
    if is_directory:
        output.mkdir()
        witness = output / "witness.bin"
    else:
        witness = output
    witness.write_bytes(b"user-owned contents\0\xff")
    original = witness.read_bytes()
    with pytest.raises(ValueError, match="non vide"):
        pipeline.build_dataset(output, Config(width=800, height=1100, columns=4))
    assert witness.read_bytes() == original
    if is_directory:
        assert list(output.iterdir()) == [witness]


@pytest.mark.parametrize("overrides", [{"width": 0}, {"columns": 7}, {"dpi": 0}, {"seed": -1}])
def test_invalid_configuration_fails_before_destination_creation(tmp_path, overrides):
    output = tmp_path / "should_not_exist"
    values = {"width": 800, "height": 1100, "columns": 4, **overrides}
    with pytest.raises(ValueError):
        pipeline.build_dataset(output, Config(**values))
    assert not output.exists()


@pytest.mark.parametrize("count,jobs", [(0, 1), (1001, 1), (1, 0), (1, 5)])
def test_invalid_execution_limits_fail_before_writes(tmp_path, count, jobs):
    output = tmp_path / "should_not_exist"
    with pytest.raises(ValueError):
        pipeline.build_dataset(output, Config(width=800, height=1100, columns=4), count, jobs)
    assert not output.exists()


def test_failed_export_leaves_no_accepted_partial_dataset(tmp_path, monkeypatch):
    from mille_feuilles import exports

    def storage_failure(page, root):
        raise OSError("simulated export storage failure")

    monkeypatch.setattr(exports, "export_page", storage_failure)
    output = tmp_path / "interrupted"
    with pytest.raises(OSError, match="storage failure"):
        pipeline.build_dataset(output, Config(width=800, height=1100, columns=4), count=1)
    assert list((output / "images").glob("*.png")), "Failure must occur after real rendering"
    assert not (output / "manifest.json").exists()
    assert not (output / "qa/report.json").exists()
    assert validate_dataset(output)["status"] == "fail"
    before = {str(p.relative_to(output)): sha256(p) for p in output.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="non vide"):
        pipeline.build_dataset(output, Config(width=800, height=1100, columns=4))
    after = {str(p.relative_to(output)): sha256(p) for p in output.rglob("*") if p.is_file()}
    assert before == after


def test_failed_page_cancels_queued_work_waits_for_active_pages_and_preserves_error(
    tmp_path, monkeypatch
):
    from mille_feuilles import exports, validation

    task_count = 12
    submitted = []
    submitted_lock = Lock()
    all_submitted = Event()
    queue_cancelled = Event()
    active_started = Event()
    release_active = Event()
    build_finished = Event()
    entered = [Event() for _ in range(task_count)]
    started, finished = set(), set()
    work_lock = Lock()
    primary = OSError("first page export failed")
    secondary = RuntimeError("an active page also failed while draining")
    outcome = {}

    def observe_completion(_future):
        with submitted_lock:
            if (
                len(submitted) == task_count
                and any(future.cancelled() for future in submitted)
                and all(future.running() or future.done() for future in submitted)
            ):
                queue_cancelled.set()

    class ObservedExecutor(ThreadPoolExecutor):
        # Observe public Future states; execution and cancellation use the real
        # executor, so shutdown(cancel_futures=True) would satisfy this too.
        def submit(self, fn, /, *args, **kwargs):
            future = super().submit(fn, *args, **kwargs)
            with submitted_lock:
                submitted.append(future)
                if len(submitted) == task_count:
                    all_submitted.set()
            future.add_done_callback(observe_completion)
            return future

    def controlled_render(_config, index, _assets, _root):
        entered[index].set()
        if index == 0:
            assert active_started.wait(5), "A second page must already be active"
            assert all_submitted.wait(5), "There must be queued work to cancel"
            raise primary
        with work_lock:
            started.add(index)
        active_started.set()
        assert release_active.wait(10), "The test did not release active work"
        with work_lock:
            finished.add(index)
        if index == 1:
            raise secondary
        return {"page_id": f"mf_{index:04d}", "words": []}

    def run_build():
        try:
            outcome["result"] = pipeline.build_dataset(
                tmp_path / "cancelled_campaign",
                Config(width=800, height=1100, columns=4),
                count=task_count,
                jobs=2,
            )
        except BaseException as exc:
            outcome["error"] = exc
        finally:
            build_finished.set()

    monkeypatch.setattr(pipeline, "ThreadPoolExecutor", ObservedExecutor)
    monkeypatch.setattr(pipeline, "render_page", controlled_render)
    monkeypatch.setattr(validation, "validate_page", lambda _page: [])
    monkeypatch.setattr(exports, "export_page", lambda _page, _root: None)
    monkeypatch.setattr(pipeline, "overlay", lambda _page, _root: None)
    worker = Thread(target=run_build, daemon=True)
    worker.start()
    try:
        assert queue_cancelled.wait(5), "Queued pages should be cancelled after the first error"
        for index, future in enumerate(submitted):
            if future.running():
                assert entered[index].wait(5)
        with work_lock:
            active_before_release = set(started)
        assert active_before_release
        assert len(active_before_release) < task_count - 1
        assert not build_finished.is_set(), "The pipeline must wait for already-active pages"
    finally:
        release_active.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    assert outcome.get("error") is primary, "A later error must not replace the original exception"
    assert started == active_before_release, "No queued page may start after cancellation"
    assert finished == started, "Every already-active page must be allowed to finish"
    assert any(future.cancelled() for future in submitted)
    assert not (tmp_path / "cancelled_campaign/manifest.json").exists()
    assert not (tmp_path / "cancelled_campaign/qa/report.json").exists()


def test_compare_detects_removed_image(repeated_lots, tmp_path):
    first, _, _, _, _ = repeated_lots
    broken = tmp_path / "broken"
    shutil.copytree(first, broken)
    missing = next((broken / "images").glob("*.png"))
    relative = str(missing.relative_to(broken))
    missing.unlink()
    comparison = pipeline.compare_lots(first, broken)
    assert comparison["status"] == "fail"
    details = comparison.get("mismatches", []) + comparison.get("errors", [])
    assert any(relative in detail for detail in details)


def test_compare_does_not_accept_two_identical_incomplete_lots(tmp_path):
    directories = [tmp_path / "one", tmp_path / "two"]
    for directory in directories:
        directory.mkdir()
        (directory / "manifest.json").write_text(json.dumps({"artifacts": []}))
    assert pipeline.compare_lots(*directories)["status"] == "fail"
