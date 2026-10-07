"""CLI acceptance/rejection through real process exit status and JSON output."""

import json
import shutil
import subprocess
import sys

import pytest

from mille_feuilles.cli import main
from mille_feuilles.validation import load_json


def invoke(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "mille_feuilles.cli", *map(str, arguments)],
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture(scope="module")
def generated_lot(tmp_path_factory):
    output = tmp_path_factory.mktemp("cli") / "one_page"
    result = invoke(
        "generate",
        "--output",
        output,
        "--pages",
        1,
        "--width",
        800,
        "--height",
        1100,
        "--columns",
        4,
        "--degradation",
        "clean",
        "--seed",
        813,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["status"] == "pass", report
    return output, result


def test_generate_separates_json_result_from_progress(generated_lot):
    output, result = generated_lot
    assert json.loads(result.stdout)["statistics"]["pages"] == 1
    assert "1/1 pages" in result.stderr
    assert (output / "qa/report.json").is_file()
    assert load_json(output / "qa/report.json")["status"] == "pass"


def test_validate_valid_lot_has_zero_exit_status_and_json(generated_lot):
    output, _ = generated_lot
    result = invoke("validate", output)
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["status"] == "pass"
    assert any(
        check["name"] == "exports" and check["status"] == "pass" for check in report["checks"]
    )


def test_validate_duplicate_json_key_exits_nonzero(generated_lot, tmp_path):
    original, _ = generated_lot
    broken = tmp_path / "duplicate"
    shutil.copytree(original, broken)
    (broken / "manifest.json").write_text('{"schema_version":"0.2.0","schema_version":"0.2.0"}')
    result = invoke("validate", broken)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "fail"
    assert any("duplicate JSON key" in error for error in report["errors"])
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("target", ["images", "exports/alto"])
def test_validate_tampered_image_or_xml_exits_nonzero(generated_lot, tmp_path, target):
    original, _ = generated_lot
    broken = tmp_path / "tampered"
    shutil.copytree(original, broken)
    path = next((broken / target).glob("*"))
    path.write_bytes(path.read_bytes() + b"tamper")
    result = invoke("validate", broken)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "fail"
    assert any("SHA-256 mismatch" in error for error in report["errors"])


def test_validate_partial_output_exits_nonzero(tmp_path):
    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "config.json").write_text("{}")
    result = invoke("validate", partial)
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "fail"


def test_generate_nonempty_destination_is_controlled_error(tmp_path, capsys):
    output = tmp_path / "occupied"
    output.mkdir()
    witness = output / "mine.txt"
    witness.write_text("keep this exactly")
    status = main(
        [
            "generate",
            "--output",
            str(output),
            "--width",
            "800",
            "--height",
            "1100",
            "--columns",
            "4",
        ]
    )
    captured = capsys.readouterr()
    assert status == 2
    assert "non vide" in captured.err
    assert witness.read_text() == "keep this exactly"
    assert list(output.iterdir()) == [witness]


def test_generate_invalid_config_does_not_leave_output(tmp_path, capsys):
    output = tmp_path / "invalid"
    status = main(["generate", "--output", str(output), "--width", "0"])
    captured = capsys.readouterr()
    assert status == 2
    assert "Erreur" in captured.err
    assert not output.exists()


def test_compare_valid_lot_to_copy_succeeds(generated_lot, tmp_path):
    original, _ = generated_lot
    clone = tmp_path / "clone"
    shutil.copytree(original, clone)
    result = invoke("compare", original, clone)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout)["status"] == "pass"


def test_compare_malformed_manifest_is_controlled_error(tmp_path, capsys):
    first, second = tmp_path / "first", tmp_path / "second"
    for directory in (first, second):
        directory.mkdir()
        (directory / "manifest.json").write_text("{}")
    status = main(["compare", str(first), str(second)])
    captured = capsys.readouterr()
    assert status != 0
    assert "Traceback" not in captured.err
    if captured.out:
        assert json.loads(captured.out)["status"] == "fail"


def test_generate_with_invalid_final_xml_reports_failure(tmp_path, monkeypatch, capsys):
    from mille_feuilles import exports

    real_export = exports.export_page

    def damaged_export(page, root):
        paths = real_export(page, root)
        # Damage occurs before manifest hashing: integrity hashes alone would
        # accept this lot. The final real XML validation must reject it.
        (root / paths["alto"]).write_text("not an XML document")
        return paths

    monkeypatch.setattr(exports, "export_page", damaged_export)
    output = tmp_path / "broken_export"
    status = main(
        [
            "generate",
            "--output",
            str(output),
            "--pages",
            "1",
            "--width",
            "800",
            "--height",
            "1100",
            "--columns",
            "4",
            "--degradation",
            "clean",
        ]
    )
    captured = capsys.readouterr()
    assert status == 1
    report = json.loads(captured.out)
    assert report["status"] == "fail"
    checks = {check["name"]: check["status"] for check in report["checks"]}
    assert checks["file_hashes"] == "pass"
    assert checks["exports"] == "fail"
    assert load_json(output / "qa/report.json")["status"] == "fail"
