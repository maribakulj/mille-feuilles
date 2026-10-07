#!/usr/bin/env python3
"""Bounded CLI acceptance for layout v2 on a clean, frozen source revision.

Uses only bundled original demonstration texts. Preserves every output on
failure. Visual inspection is separate and is never inferred from these checks.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

from PIL import Image

from mille_feuilles.degrade import load_profile
from mille_feuilles.io import ROOT, sha256, write_json
from mille_feuilles.pipeline import environment
from mille_feuilles.render import PROFILE_LAYOUT, PROFILE_MEASURED
from mille_feuilles.validation import load_json, validate_dataset

SEED = 20261007
MIN_FREE = 1_000_000_000
MAX_BYTES = 200_000_000
LEGACY_COMMIT = 'cb24e39e42d6c7519a32f6b70bcbccced6e13f36'
LEGACY_ARCHIVE = 'docs/reports/lot3/acceptance/lots/compact-identity-x1/manifest.json'


def snapshot(root):
    return {p.relative_to(root).as_posix(): sha256(p)
            for p in sorted(root.rglob('*')) if p.is_file()}


def source_state():
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True))
    return {'commit': commit, 'dirty': dirty, 'environment': environment(),
            'scripts': {name: sha256(ROOT / name) for name in
                        ('tools/accept_layout.py', 'tools/reproduce_pilot.py')}}


def bundled_inputs():
    catalog = load_json(ROOT / 'assets/catalog.json')
    texts = [a for a in catalog['assets'] if a['kind'] == 'text']
    if len(texts) != 3 or any(a['metadata'].get('historical_corpus') is not False for a in texts):
        raise ValueError('Acceptance requires exactly the three original demonstration texts')
    paths = {'assets/catalog.json', 'profiles/identity.json', 'profiles/controlled-v1.json'}
    for asset in catalog['assets']:
        paths.add(asset['path'])
        paths.update(item['path'] for item in asset['metadata'].get('evidence_files', []))
    return {relative: sha256(ROOT / relative) for relative in sorted(paths)}


def composition(page):
    value = {key: deepcopy(page[key]) for key in
             ('articles', 'blocks', 'lines', 'words', 'reading_order')}
    for item in value['words'] + value['lines']:
        item.pop('legibility')
    value['text_spans'] = page['provenance']['text_spans']
    value['layout'] = page['provenance']['parameters']['layout']
    return value


def unrotate(page, polygon):
    angle = math.radians(page['provenance']['parameters']['angle_degrees'])
    c, s = math.cos(angle), math.sin(angle)
    cx, cy = page['image']['width'] / 2, page['image']['height'] / 2
    return [[c * (x - cx) - s * (y - cy) + cx, s * (x - cx) + c * (y - cy) + cy]
            for x, y in polygon]


class Acceptance:
    def __init__(self, root, source, inputs, legacy):
        self.root, self.source, self.inputs = root, source, inputs
        self.legacy = legacy
        self.legacy_snapshot = snapshot(legacy)
        self.report = {
            'format': 'mille-feuilles-layout-acceptance', 'version': '1', 'status': 'fail',
            'started_at_utc': datetime.now(timezone.utc).isoformat(),
            'seed': SEED, 'source': source, 'inputs': inputs,
            'checks': [], 'commands': [], 'lots': {}, 'errors': [],
            'scope': 'Bundled original demonstration texts; no real corpus or model evaluation',
            'visual_review': {'status': 'not_run', 'note': 'Inspect final pages and native crops separately'},
            'resource_note': 'Command times include exports/validation; child RSS is a cumulative maximum',
            'legacy_reference': {'path': str(legacy), 'commit': LEGACY_COMMIT,
                                 'manifest_sha256': sha256(legacy / 'manifest.json'),
                                 'scope': 'Measured non-v2 path only; manifest/environment may change'},
            'sampling_comparisons': [], 'bands': [],
        }

    def check(self, condition, description):
        if not condition:
            raise ValueError(description)
        self.report['checks'].append(description)

    def guard(self):
        self.check(source_state() == self.source, 'Clean source revision and environment unchanged')
        self.check(bundled_inputs() == self.inputs, 'Original inputs unchanged')
        self.check(snapshot(self.legacy) == self.legacy_snapshot, 'Legacy reference remains unchanged')
        size = sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
        self.check(size < MAX_BYTES, f'Volume {size} bytes below {MAX_BYTES} (between commands)')

    def run(self, name, arguments, script=None, expected_exit=0):
        self.guard()
        command = [sys.executable]
        command += [str(script)] if script else ['-m', 'mille_feuilles.cli']
        command += [str(arg) for arg in arguments]
        stdout, stderr = self.root / f'logs/{name}.json', self.root / f'logs/{name}.stderr.log'
        stdout.parent.mkdir(exist_ok=True)
        entry = {'name': name, 'argv': command, 'cwd': str(ROOT),
                 'stdout': str(stdout.relative_to(self.root)), 'stderr': str(stderr.relative_to(self.root))}
        self.report['commands'].append(entry)
        print(f'Acceptation mise en page : {name}', file=sys.stderr, flush=True)
        started = time.perf_counter()
        with stdout.open('xb') as out, stderr.open('xb') as err:
            result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, check=False)
        entry.update(exit_code=result.returncode, elapsed_seconds=time.perf_counter() - started)
        self.guard()
        self.check(result.returncode == expected_exit, f'{name}: CLI exit code {expected_exit}')
        if expected_exit:
            self.check(stdout.stat().st_size == 0, f'{name}: no success JSON emitted')
            return None
        report = load_json(stdout)
        self.check(report.get('status') == 'pass', f'{name}: report passed')
        write_json(self.root / f'reports/{name}.json', report)
        return report

    def generate(self, name, profile, *, width=1200, height=1656, count=2, source=ROOT, jobs=1, columns=4):
        target = self.root / f'lots/{name}'
        report = self.run(name, ['generate', '--output', target, '--assets-root', source,
                                '--pages', count, '--width', width, '--height', height, '--dpi', 67,
                                '--seed', SEED, '--jobs', jobs,
                                '--layout-profile', PROFILE_LAYOUT, '--degradation-profile', profile,
                                *(['--columns', columns] if columns is not None else [])])
        self.check(all(c['status'] == 'pass' for c in report['checks']), f'{name}: all dataset checks passed')
        manifest = load_json(target / 'manifest.json')
        self.check(manifest['profile'] == PROFILE_LAYOUT, f'{name}: layout v2 manifest')
        self.check(manifest['generator']['commit'] == self.source['commit'] and not manifest['generator']['dirty'],
                   f'{name}: recorded clean production commit')
        self.check(load_json(target / 'environment.json') == self.source['environment'],
                   f'{name}: recorded frozen environment')
        template = load_json(target / 'assets/template.json')
        self.check(template['id'] == 'template_press_v2' and template['calibrated'] is False,
                   f'{name}: declared uncalibrated template')
        pages = [load_json(target / p['path']) for p in manifest['pages']]
        self.check(len(pages) == count, f'{name}: exact page count')
        names = [check['name'] for check in report['checks']]
        required = {'layout_profile', 'degradation_profile', 'exports', 'export_inventory'}
        required |= {f"{kind}:{p['page_id']}" for p in pages for kind in ('page', 'page_files')}
        self.check(len(names) == len(set(names)) and required <= set(names),
                   f'{name}: named profile, page, file and export checks present')
        for page in pages:
            typography = page['provenance']['parameters']['layout_typography']
            self.check(len({t['normal_body_size'] for t in typography.values()}) == 1,
                       f"{name}/{page['page_id']}: shared normal body size")
            self.inspect_bands(name, page)
        self.report['lots'][name] = {
            'path': str(target.relative_to(self.root)), 'manifest_sha256': sha256(target / 'manifest.json'),
            'pages': count, 'words': sum(len(p['words']) for p in pages),
            'statistics': report['statistics'],
            'features_by_page': [{
                'page_id': p['page_id'],
                'zones': [z['id'] for z in p['provenance']['parameters']['layout']['zones']],
                'headlines': [a['id'] for a in p['articles'] if a.get('extensions', {}).get('mf:layout', {}).get('headline')],
                'boxed_ads': [a['id'] for a in p['articles'] if a.get('extensions', {}).get('mf:layout', {}).get('box')],
            } for p in pages],
        }
        return target, pages

    def inspect_bands(self, name, page):
        from mille_feuilles.layout import check_plan

        plan = page['provenance']['parameters']['layout']
        self.check(check_plan(plan) == [], f"{name}/{page['page_id']}: independent plan check")
        blocks = {b['id']: b for b in page['blocks']}
        for article in page['articles']:
            meta = article.get('extensions', {}).get('mf:layout', {})
            headline = meta.get('headline')
            if not headline:
                continue
            zone = next(z for z in plan['zones'] if z['id'] == meta['zone_id'])
            body = [blocks[bid] for bid in article['block_ids'] if bid != headline['block_id']]
            counts = [len(b['line_ids']) for b in body]
            k = zone['headline_span']
            self.check(len(body) == k and min(counts) >= 2 and max(counts) - min(counts) <= 1,
                       f"{name}/{article['id']}: one balanced body block per covered column")
            for index, block in enumerate(body):
                points = unrotate(page, block['polygon'])
                left, right = zone['columns'][index]
                self.check(min(p[0] for p in points) >= left - 0.5 and max(p[0] for p in points) <= right + 0.5,
                           f"{name}/{block['id']}: correct covered column")
                self.check(min(p[1] for p in points) >= zone['headline_reserved'][3] - 0.5
                           and max(p[1] for p in points) <= zone['headline_body_band'][3] + 0.5,
                           f"{name}/{block['id']}: body confined vertically to its band")
            for other in page['articles']:
                if other['id'] == article['id'] or other.get('extensions', {}).get('mf:layout', {}).get('zone_id') != zone['id']:
                    continue
                for bid in other['block_ids']:
                    points = unrotate(page, blocks[bid]['polygon'])
                    if (min(p[0] for p in points) < zone['headline_body_band'][2] - 0.5
                            and max(p[0] for p in points) > zone['headline_body_band'][0] + 0.5):
                        self.check(min(p[1] for p in points) >= zone['headline_body_band'][3] - 0.5,
                                   f'{name}/{bid}: ordinary article begins below reserved band')
            ink_bottom = max(p[1] for b in body for p in unrotate(page, b['polygon']))
            typo = page['provenance']['parameters']['layout_typography'][meta['zone_id']]
            spacing = typo['line_spacing_small' if meta['small_body'] else 'line_spacing_normal']
            preparation_bottom = zone['headline_body_band'][3] - 0.6 * spacing
            self.report['bands'].append({
                'lot': name, 'page_id': page['page_id'], 'article_id': article['id'],
                'line_counts': counts, 'body_preparation_bottom': preparation_bottom,
                'real_polygon_bottom': ink_bottom, 'gap_to_preparation_px': preparation_bottom - ink_bottom,
                'preparation_derivation': 'band bottom minus 0.6 times recorded body line spacing',
                'scope': 'Measured difference, no acceptance threshold imposed',
            })

    def compare_sampling(self, a, b):
        self.check(a['reading_order'] == b['reading_order'], f"{a['page_id']}: same reading order across factors")
        for collection, keys in (('lines', ('id', 'block_id', 'text', 'word_ids', 'extensions')),
                                 ('blocks', ('id', 'category', 'article_id', 'line_ids'))):
            self.check([{k: x.get(k) for k in keys} for x in a[collection]] ==
                       [{k: x.get(k) for k in keys} for x in b[collection]],
                       f"{a['page_id']}: same {collection} identities and content across factors")
        heights = [abs(x[1] - y[1]) for la, lb in zip(a['lines'], b['lines'])
                   for x, y in zip(unrotate(a, la['baseline']), unrotate(b, lb['baseline']))]
        self.check(max(heights) <= 1e-5, f"{a['page_id']}: same baseline heights before rotation (1e-5 px)")
        delta = max(abs(x - y) for wa, wb in zip(a['words'], b['words'])
                    for pa, pb in zip(wa['polygon'], wb['polygon']) for x, y in zip(pa, pb))
        endpoint_delta = max(abs(x - y) for la, lb in zip(a['lines'], b['lines'])
                             for pa, pb in zip(la['baseline'], lb['baseline']) for x, y in zip(pa, pb))
        self.report['sampling_comparisons'].append({'page_id': a['page_id'],
                                                   'max_word_coordinate_difference_px': delta,
                                                   'max_baseline_height_difference_px': max(heights),
                                                   'max_baseline_endpoint_difference_px': endpoint_delta,
                                                   'polygon_difference_threshold': None})

    def legacy_replay(self):
        config = load_json(self.legacy / 'config.json')['render']
        target = self.root / 'legacy-compatible'
        self.run('legacy-compatible', ['generate', '--output', target, '--pages', 1,
                                      '--assets-root', self.legacy,
                                      '--width', config['width'], '--height', config['height'],
                                      '--dpi', config['dpi'],
                                      *(['--columns', config['columns']] if config['columns'] is not None else []),
                                      '--seed', config['seed'], '--jobs', 1,
                                      '--degradation-profile', self.legacy / 'provenance/degradation-profile.json'])
        self.check(load_json(target / 'manifest.json')['profile'] == PROFILE_MEASURED,
                   'Legacy replay uses measured non-v2 profile')
        for relative in ('images/mf_0000.png', 'pages/mf_0000.json', 'qa/masks/mf_0000.png',
                         'qa/diagnostics/mf_0000.json'):
            self.check((target / relative).read_bytes() == (self.legacy / relative).read_bytes(),
                       f'Legacy measured non-v2 remains byte-identical: {relative}')

    def execute(self):
        rejected = self.root / 'must-not-exist'
        self.run('reject-missing-photometric-profile', ['generate', '--output', rejected,
                                                      '--layout-profile', PROFILE_LAYOUT], expected_exit=2)
        self.check(not rejected.exists(), 'Missing photometric profile refused before destination creation')
        self.legacy_replay()
        profiles = {}
        for name, factor in (('identity', 1), ('identity', 2), ('controlled-v1', 2)):
            profile = deepcopy(load_profile(name))
            profile['oversampling'] = factor
            path = self.root / f'sources/{name}-x{factor}.json'
            write_json(path, profile)
            profiles[name, factor] = path
        one, pages_one = self.generate('compact-identity-x1', profiles['identity', 1])
        two, pages_two = self.generate('compact-identity-x2', profiles['identity', 2])
        controlled, pages_controlled = self.generate('compact-controlled-x2', profiles['controlled-v1', 2])
        features = self.report['lots']['compact-identity-x2']['statistics']['layout']
        for key in ('wide_headlines', 'boxed_ads', 'small_body_articles'):
            self.check(features[key] > 0, f'Observed feature: {key}')
        self.check(features['zones'].get('rez_de_chaussee', 0) > 0, 'Observed lower column zone')
        for a, b, c in zip(pages_one, pages_two, pages_controlled):
            self.compare_sampling(a, b)
            self.check(composition(b) == composition(c), f"{b['page_id']}: photometric pair has identical composition")
            self.check(a['provenance']['parameters']['layout'] == b['provenance']['parameters']['layout'],
                       f"{a['page_id']}: same layout plan at x1 and x2")
            self.check([(w['id'], w['text']) for w in a['words']] == [(w['id'], w['text']) for w in b['words']],
                       f"{a['page_id']}: same words at x1 and x2")
            mask = b['extensions']['mf:diagnostics']['mask_path']
            self.check((two / mask).read_bytes() == (controlled / mask).read_bytes(),
                       f"{b['page_id']}: ideal mask independent of photometry")
            with Image.open(two / b['image']['path']) as image_a, Image.open(controlled / c['image']['path']) as image_b:
                self.check(image_a.convert('L').tobytes() != image_b.convert('L').tobytes(),
                           f"{b['page_id']}: decoded photometric pixels differ")
        self.generate('pilot-controlled-x2', profiles['controlled-v1', 2], width=2680, height=3698, count=1, columns=None)
        replay, _ = self.generate('replay-workers2', controlled / 'provenance/degradation-profile.json',
                                  source=controlled, jobs=2)
        self.run('compare-replay', ['compare', controlled, replay])
        self.check(snapshot(controlled) == snapshot(replay), 'Every source and two-worker replay file byte-identical')
        recreated = self.root / 'reproduced'
        self.run('reproduce', [controlled, '--output', recreated, '--report', self.root / 'reports/reproduction.json'],
                 script=ROOT / 'tools/reproduce_pilot.py')
        for page in pages_controlled:
            for relative in (page['image']['path'], f"pages/{page['page_id']}.json",
                             page['extensions']['mf:diagnostics']['mask_path'],
                             page['extensions']['mf:diagnostics']['path']):
                self.check((controlled / relative).read_bytes() == (recreated / relative).read_bytes(),
                           f'Reproduction byte-identical: {relative}')
        self.guard()
        self.report['status'] = 'pass'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--legacy-reference', type=Path, required=True,
                        help='Preserved compact-identity-x1 lot from the committed lot-3 acceptance')
    args = parser.parse_args()
    root = args.output.absolute()
    try:
        if root.exists():
            raise ValueError(f'Destination exists; no overwrite: {root}')
        source, inputs = source_state(), bundled_inputs()
        if source['dirty']:
            raise ValueError('A clean committed source revision is required')
        free = shutil.disk_usage(ROOT).free
        if free < MIN_FREE:
            raise ValueError(f'At least {MIN_FREE} free bytes required; found {free}')
        legacy = args.legacy_reference.resolve()
        resolved_output = root.resolve()
        if resolved_output.is_relative_to(legacy) or legacy.is_relative_to(resolved_output):
            raise ValueError('Destination and preserved legacy reference must be disjoint')
        archived = ROOT / LEGACY_ARCHIVE
        if sha256(legacy / 'manifest.json') != sha256(archived):
            raise ValueError('Legacy manifest differs from the committed lot-3 proof')
        reference_manifest = load_json(archived)
        if reference_manifest['generator']['commit'] != LEGACY_COMMIT:
            raise ValueError('Unexpected legacy production revision')
        if validate_dataset(legacy)['status'] != 'pass':
            raise ValueError('Legacy reference fails read-only validation')
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'Refus : {exc}', file=sys.stderr)
        return 2
    root.mkdir(parents=True)
    acceptance = Acceptance(root, source, inputs, legacy)
    try:
        acceptance.execute()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError) as exc:
        acceptance.report['errors'].append(f'{type(exc).__name__}: {exc}')
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    acceptance.report['resources'] = {
        'child_maxrss_raw': usage.ru_maxrss, 'child_maxrss_unit': 'bytes' if sys.platform == 'darwin' else 'KiB',
        'written_bytes_before_final_report': sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),
        'limit_bytes': MAX_BYTES, 'volume_scope': 'Between commands; not an atomic subprocess quota',
    }
    write_json(root / 'acceptance.json', acceptance.report)
    final_size = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    if final_size >= MAX_BYTES:
        acceptance.report['status'] = 'fail'
        acceptance.report['errors'].append(f'Final report exceeds volume budget: {final_size}')
        write_json(root / 'acceptance.json', acceptance.report)
    print(json.dumps({'status': acceptance.report['status'], 'path': str(root / 'acceptance.json'),
                      'visual_review': 'not_run', 'errors': acceptance.report['errors']}, ensure_ascii=False))
    return 0 if acceptance.report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
