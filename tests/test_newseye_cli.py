"""CLI routing and legacy failure behavior without exporting or rendering pages."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from mille_feuilles import cli


@pytest.mark.parametrize('status,code', [('pass', 0), ('fail', 1)])
def test_export_newseye_routes_selection_without_building_dataset(monkeypatch, capsys, status, code):
    calls = []

    def export_bundle(source, output, *, page_ids):
        calls.append((source, output, page_ids))
        return {'status': status, 'errors': [] if status == 'pass' else ['fixture refusal']}

    def forbidden(*args, **kwargs):
        pytest.fail('A projection command must not call the raster generator')

    monkeypatch.setitem(sys.modules, 'mille_feuilles.newseye_bundle', SimpleNamespace(export_bundle=export_bundle))
    monkeypatch.setattr(cli, 'build_dataset', forbidden)
    assert cli.main(['export-newseye', '--from', 'source', '--output', 'target',
                     '--page', 'mf_0003', '--page', 'mf_0001']) == code
    assert calls == [(Path('source'), Path('target'), ['mf_0003', 'mf_0001'])]
    assert json.loads(capsys.readouterr().out)['status'] == status


def test_validate_routes_recognized_projection_bundle(tmp_path, monkeypatch, capsys):
    (tmp_path / 'manifest.json').write_text(json.dumps({'format': 'mille-feuilles-newseye-bundle'}))
    calls = []

    def validate_bundle(root):
        calls.append(root)
        return {'status': 'fail', 'errors': ['incomplete projection fixture']}

    def forbidden(*args, **kwargs):
        pytest.fail('A projection manifest must use the projection validator')

    monkeypatch.setitem(sys.modules, 'mille_feuilles.newseye_bundle', SimpleNamespace(validate_bundle=validate_bundle))
    monkeypatch.setattr(cli, 'validate_dataset', forbidden)
    assert cli.main(['validate', str(tmp_path)]) == 1
    assert calls == [tmp_path]
    assert json.loads(capsys.readouterr().out)['errors'] == ['incomplete projection fixture']


@pytest.mark.parametrize('manifest', [None, '{broken', '[]', '{"profile":"legacy"}'])
def test_legacy_validation_keeps_its_structured_failures(tmp_path, monkeypatch, capsys, manifest):
    if manifest is not None:
        (tmp_path / 'manifest.json').write_text(manifest)
    calls = []

    def validate_dataset(root):
        calls.append(root)
        return {'status': 'fail', 'errors': ['original validator detail']}

    monkeypatch.setattr(cli, 'validate_dataset', validate_dataset)
    assert cli.main(['validate', str(tmp_path)]) == 1
    assert calls == [tmp_path]
    captured = capsys.readouterr()
    assert not captured.err
    assert json.loads(captured.out)['errors'] == ['original validator detail']
