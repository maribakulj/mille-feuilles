"""Metadata-only refusal checks: never launch acceptance or generate a raster."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from mille_feuilles.io import ROOT


@pytest.fixture(scope="module")
def accept_tool():
    spec = importlib.util.spec_from_file_location(
        "accept_layout_preflight_tests", ROOT / "tools/accept_layout.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(root):
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[relative] = ("symlink", str(path.readlink()))
        elif path.is_dir():
            result[relative] = ("directory",)
        else:
            result[relative] = ("file", path.read_bytes())
    return result


@pytest.mark.parametrize("through_symlink", [False, True], ids=["direct", "symlink"])
def test_nested_output_is_rejected_before_any_write(
    tmp_path, monkeypatch, capsys, accept_tool, through_symlink,
):
    tool = accept_tool
    repository = tmp_path / "repository"
    legacy = tmp_path / "preserved-legacy"
    legacy.mkdir()
    manifest = ('{"generator":{"commit":"' + tool.LEGACY_COMMIT + '"}}\n').encode()
    (legacy / "manifest.json").write_bytes(manifest)
    (legacy / "original-evidence.txt").write_bytes(b"Preserved synthetic evidence\n")
    archived = repository / tool.LEGACY_ARCHIVE
    archived.parent.mkdir(parents=True)
    archived.write_bytes(manifest)
    alias = tmp_path / "legacy-alias"
    if through_symlink:
        alias.symlink_to(legacy, target_is_directory=True)
    output = (alias if through_symlink else legacy) / "new-acceptance"

    observed = []

    def source_state():
        observed.append("source_state")
        return {"commit": "metadata-only", "dirty": False}

    def inputs():
        observed.append("bundled_inputs")
        return {"scope": "metadata-only original fixture"}

    def validate_dataset(path):
        observed.append(("validate_dataset", Path(path)))
        return {"status": "pass"}

    def forbidden(*_args, **_kwargs):
        pytest.fail("An overlapping destination must never reach acceptance or generation")

    monkeypatch.setattr(tool, "ROOT", repository)
    monkeypatch.setattr(tool, "source_state", source_state)
    monkeypatch.setattr(tool, "bundled_inputs", inputs)
    monkeypatch.setattr(tool, "validate_dataset", validate_dataset)
    monkeypatch.setattr(tool, "Acceptance", forbidden)
    monkeypatch.setattr(tool.subprocess, "run", forbidden)
    monkeypatch.setattr(tool, "write_json", forbidden)
    # Isolate the path guard from host free space. Acceptance construction,
    # subprocesses and report writes are forbidden: no real workload can use
    # this synthetic metadata-only capacity, and production guards stay intact.
    monkeypatch.setattr(tool.shutil, "disk_usage", lambda _path: SimpleNamespace(free=tool.MIN_FREE + 1))
    monkeypatch.setattr(tool.sys, "argv", [
        "accept_layout.py", "--output", str(output), "--legacy-reference", str(legacy),
    ])
    before = snapshot(tmp_path)

    assert tool.main() == 2

    captured = capsys.readouterr()
    assert "must be disjoint" in captured.err
    assert captured.out == ""
    assert observed == ["source_state", "bundled_inputs"]
    assert not output.exists()
    assert not (legacy / "new-acceptance").exists()
    assert snapshot(tmp_path) == before
