"""JSON geometry and metadata tests only; no page images are generated."""
from copy import deepcopy
import math
import random

from PIL import ImageFont
import pytest

from mille_feuilles import layout, validation
from mille_feuilles.io import ROOT as REPO

FONT = REPO / 'assets/fonts/oldstandardtt/OldStandard-Regular.ttf'


def rect(values):
    left, top, right, bottom = values
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


def fixture_page(angle=0, factor=1):
    options = deepcopy(layout.DEFAULT_OPTIONS)
    options.update(main_columns={'choice': [4], 'weights': [1]},
                   rez_de_chaussee_columns={'choice': [3], 'weights': [1]},
                   rez_de_chaussee_probability=1, headline_probability=1,
                   headline_span={'choice': [2], 'weights': [1]})
    draws = layout.draw_layout(random.Random(3), options, width=2680, height=3698, margin=94,
                               gutter=24, column_ok=lambda _: True)
    typography = {}
    main_width = draws['zones'][0]['columns'][0][1] - draws['zones'][0]['columns'][0][0]
    normal = max(10, round(main_width / 20))
    for zone in draws['zones']:
        small = layout.small_body_size(normal, 0.82)
        metrics = {'normal_body_size': normal, 'small_body_size': small}
        for name, size in [('normal', normal), ('small', small)]:
            font = ImageFont.truetype(str(FONT), size, layout_engine=ImageFont.Layout.BASIC)
            asc, desc = font.getmetrics()
            metrics['line_spacing_' + name] = max(size * 1.14, (asc + desc) * 0.92)
        typography[zone['id']] = metrics
    minimum = 6 * max(t['line_spacing_normal'] for t in typography.values())
    plan = layout.place_zones(draws, top=330, bottom=3604, min_zone_height=minimum)
    plan = layout.reserve_headline(plan, 'main', 420, 10)
    spacing = typography['main']['line_spacing_normal']
    plan = layout.reserve_headline_band(plan, 'main', 480 + spacing, .6 * spacing, spacing)
    main, lower = plan['zones']
    main_size, lower_size = [typography[z]['normal_body_size'] for z in ['main', 'rez_de_chaussee']]
    reserve = main['headline_reserved']
    def article_meta(name, size):
        return {'zone_id': name, 'body_font_size': size, 'small_body_requested': False,
                'small_body': False, 'headline': None, 'box': None}
    articles = [{'id': 'header', 'block_ids': ['header_block']},
                {'id': 'story', 'block_ids': ['title', 'body', 'body_second'], 'extensions': {'mf:layout': article_meta('main', main_size)}},
                {'id': 'ad', 'block_ids': ['ad_block'], 'extensions': {'mf:layout': article_meta('main', main_size)}},
                {'id': 'lower_story', 'block_ids': ['lower_block'], 'extensions': {'mf:layout': article_meta('rez_de_chaussee', lower_size)}}]
    articles[1]['extensions']['mf:layout']['headline'] = {'block_id': 'title', 'reservation_bbox': reserve,
                                                        'body_column_indices': [0, 1], 'attempts': 1}
    bx = main['columns'][2][0] + 10
    ad_bbox = [bx, 600, bx + 100, 630]
    outer = [bx-5, 595, bx+105, 635]
    articles[2]['extensions']['mf:layout']['box'] = {'padding': 3, 'rule_ids': ['top', 'right', 'bottom', 'left'], 'bbox': outer}
    blocks, lines, words, spans = [], [], [], []
    for bid, aid, category, bounds, size in [
        ('header_block', 'header', 'titre', [500, 130, 1000, 170], 40),
        ('title', 'story', 'titre', [94, 350, 850, 420], max(12, main_size * 2)),
        ('body', 'story', 'texte', [94, 450, 450, 480], main_size),
        ('ad_block', 'ad', 'annonce', ad_bbox, main_size),
        ('lower_block', 'lower_story', 'texte', [94, lower['bbox'][1]+20, 450, lower['bbox'][1]+50], lower_size),
    ]:
        lid, wid = bid+'_line', bid+'_word'
        blocks.append({'id': bid, 'article_id': aid, 'category': category, 'polygon': rect(bounds), 'line_ids': [lid]})
        lines.append({'id': lid, 'block_id': bid, 'polygon': rect(bounds),
                      'baseline': [[bounds[0], bounds[3]-4], [bounds[2], bounds[3]-4]],
                      'text': 'Mot', 'word_ids': [wid], 'legibility': 'readable',
                      'extensions': {'mf:font': {'asset_id': 'font_bold' if category == 'titre' else 'font_regular', 'size': size, 'layout_engine': 'BASIC'}}})
        words.append({'id': wid, 'line_id': lid, 'polygon': rect(bounds), 'text': 'Mot', 'char_span': [0, 3],
                      'legibility': 'readable', 'hyphenation': None})
        if aid != 'header':
            spans.append({'asset_id': 'text_title' if category == 'titre' else 'text_ad' if category == 'annonce' else 'text_body', 'source_document_id': 'doc', 'start': 0, 'end': 3,
                          'article_id': aid, 'block_ids': [bid]})
    # Two balanced lines in each of the headline's two columns.
    original_body = next(b for b in blocks if b['id'] == 'body')
    original_line = next(line for line in lines if line['block_id'] == 'body')
    original_word = next(word for word in words if word['line_id'] == original_line['id'])
    for suffix, column in [('',0), ('_second',1)]:
        block = original_body if column == 0 else deepcopy(original_body)
        if column:
            block['id'] = 'body_second'
            block['line_ids'] = []
            blocks.append(block)
        shift = main['columns'][column][0] - main['columns'][0][0]
        block['polygon'] = rect([94+shift,450,450+shift,480+spacing])
        for row in range(2):
            if column == 0 and row == 0:
                continue
            line,word = deepcopy(original_line),deepcopy(original_word)
            lid,wid = f'body{suffix}_line{row}',f'body{suffix}_word{row}'
            line.update(id=lid,block_id=block['id'],word_ids=[wid])
            word.update(id=wid,line_id=lid)
            for obj in [line,word]:
                obj['polygon'] = [[x+shift,y+row*spacing] for x,y in obj['polygon']]
            line['baseline'] = [[x+shift,y+row*spacing] for x,y in line['baseline']]
            lines.append(line)
            words.append(word)
            block['line_ids'].append(lid)
        if column:
            spans.append({'asset_id':'text_body','source_document_id':'doc','start':0,'end':7,
                          'article_id':'story','block_ids':['body_second']})
    next(span for span in spans if span['block_ids']==['body'])['end']=7
    x0,y0,x1,y1 = outer
    for bid,bounds in [('zone_rule', plan['zone_rules'][0]), ('top', [x0,y0,x1,y0+2]),
                       ('right', [x1-2,y0,x1,y1]), ('bottom', [x0,y1-2,x1,y1]), ('left', [x0,y0,x0+2,y1])]:
        blocks.append({'id': bid, 'article_id': None, 'category': 'separateur', 'polygon': rect(bounds), 'line_ids': []})
    for zone in plan['zones']:
        for index in range(1, len(zone['columns'])):
            middle = (zone['columns'][index-1][1]+zone['columns'][index][0])/2
            top = zone['headline_reserved'][3] if zone['headline_reserved'] and index < zone['headline_span'] else zone['bbox'][1]
            bid = zone['id']+'_column_'+str(index)
            blocks.append({'id':bid,'article_id':None,'category':'separateur','polygon':rect([middle-1,top,middle+1,zone['bbox'][3]]),'line_ids':[]})
    params = {'columns': 4, 'render_dpi': 150, 'layout_profile': validation.LAYOUT_PROFILE,
              'layout': plan, 'layout_body_ratio': 20, 'layout_typography': typography,
              'layout_rejected_candidates': {'headline': 0, 'boxed_ad': 0, 'ordinary': 0},
              'layout_termination_rejections': {'main':32,'rez_de_chaussee':32},
              'body_font_size': main_size, 'line_spacing': typography['main']['line_spacing_normal'],
              'margin': 94, 'gutter': 24, 'degradation_profile': {'profile': 'identity', 'profile_sha256': 'a'*64, 'seed': 1}}
    page = {'schema_version': '0.3.0', 'page_id': 'p1', 'profile': validation.LAYOUT_PROFILE,
            'image': {'path': 'images/p1.png', 'sha256': 'a'*64, 'width': 2680, 'height': 3698, 'color_mode': 'L', 'dpi': 150},
            'language': 'fr', 'provenance': {'seed': 1, 'template_id': 'template_press_v2',
                'asset_ids': ['text_title', 'text_ad', 'text_body', 'template_press_v2', 'font_regular', 'font_bold'], 'text_spans': spans,
                'extensions': {'mf:template_article_ids': ['header']}, 'parameters': params},
            'transforms': [], 'articles': articles, 'blocks': blocks, 'lines': lines, 'words': words,
            'reading_order': {'block_ids': ['header_block','title','body','body_second','ad_block','lower_block'],
                              'line_ids': [line['id'] for line in lines],
                              'unordered_block_ids': [b['id'] for b in blocks if b['category']=='separateur']},
            'extensions': {'mf:diagnostics': {'version': '1', 'path': 'qa/diagnostics/p1.json', 'sha256': 'a'*64,
                                            'mask_path': 'qa/masks/p1.png', 'mask_sha256': 'a'*64}}}
    page['reading_order']['line_ids'] = [lid for bid in page['reading_order']['block_ids'] for block in blocks if block['id']==bid for lid in block['line_ids']]
    # Geometry genuinely rotated, unlike a metadata-only factor declaration.
    theta = math.radians(angle)
    c,s = math.cos(theta),math.sin(theta)
    cx,cy = 1340,1849
    native = [[c,s,cx-c*cx-s*cy],[-s,c,cy+s*cx-c*cy],[0,0,1]]
    raster = [[c,s,native[0][2]*factor],[-s,c,native[1][2]*factor],[0,0,1]]
    rotation = {'kind': 'rotation', 'geometry': {'matrix': raster}, 'parameters': {}}
    page['transforms'] = [rotation]
    if factor == 2:
        page['transforms'] = [{'kind':'mf:oversampling','geometry':{'matrix':[[2,0,0],[0,2,0],[0,0,1]]},'parameters':{}},
                              rotation, {'kind':'mf:downsample','geometry':{'matrix':[[.5,0,0],[0,.5,0],[0,0,1]]},'parameters':{}}]
    def transformed(points):
        return [[round(native[0][0]*x+native[0][1]*y+native[0][2],6),
                 round(native[1][0]*x+native[1][1]*y+native[1][2],6)] for x,y in points]
    for obj in blocks+lines+words:
        obj['polygon'] = transformed(obj['polygon'])
        if 'baseline' in obj:
            obj['baseline'] = transformed(obj['baseline'])
    return page


@pytest.mark.parametrize('angle,factor', [(0,1), (.3,1), (-.3,2)])
def test_final_polygons_bind_to_unrotated_plan(angle, factor):
    assert validation.validate_page(fixture_page(angle,factor)) == []


@pytest.mark.parametrize('mutate,fragment', [
    (lambda p: p['provenance']['parameters']['layout'].update(height=3700), 'height'),
    (lambda p: p['provenance']['parameters'].update(layout_body_ratio=21), 'width/ratio'),
    (lambda p: p['provenance']['parameters']['layout'].update(min_zone_height=1), 'six normal'),
    (lambda p: p['articles'][1]['extensions']['mf:layout'].update(zone_id='rez_de_chaussee'), 'zone'),
    (lambda p: p['articles'][1]['extensions']['mf:layout'].update(small_body=True), 'small body'),
    (lambda p: p['articles'][1]['extensions']['mf:layout']['headline'].update(body_column_indices=[1,0]), 'reservation/columns'),
    (lambda p: p['articles'][2]['extensions']['mf:layout']['box'].update(padding=4), 'padding'),
    (lambda p: p['articles'][2]['extensions']['mf:layout']['box']['rule_ids'].__setitem__(0,'zone_rule'), 'frame rule'),
    (lambda p: p['lines'][2]['extensions']['mf:font'].update(size=15), 'line size'),
    (lambda p: p['articles'][1]['extensions'].pop('mf:layout'), 'zone binding'),
])
def test_semantic_mutations_are_rejected(mutate, fragment):
    page = fixture_page()
    mutate(page)
    errors = validation.validate_page(page)
    assert any(fragment in error for error in errors), errors


def test_title_cannot_replace_real_envelope_with_reservation():
    page = fixture_page()
    page['blocks'][1]['polygon'] = rect(page['provenance']['parameters']['layout']['zones'][0]['headline_reserved'])
    assert any('inflated' in error for error in validation.validate_page(page))


def test_rule_intersection_uses_polygons_and_square_pixels():
    page = fixture_page(.3, 2)
    page['blocks'][-1]['polygon'] = deepcopy(page['blocks'][2]['polygon'])
    assert any('intersects textual polygon' in error for error in validation.validate_page(page))


def test_degradation_diagnostics_remain_mandatory():
    page = fixture_page()
    page.pop('extensions')
    assert validation.validate_page(page)


def test_invalid_reserved_span_is_controlled_by_schema():
    page = fixture_page()
    page['provenance']['parameters']['layout']['zones'][0]['headline_span'] = '2'
    assert validation.validate_page(page)


def test_old_measured_profile_cannot_retain_v2_annotations():
    page = fixture_page()
    page['profile'] = validation.MEASURED_PROFILE
    params = page['provenance']['parameters']
    for name in list(params):
        if name.startswith('layout'):
            params.pop(name)
    assert validation.validate_page(page)


def fixture_context():
    assets = {'font_regular': {'id': 'font_regular', 'kind': 'font', 'path': 'assets/fonts/oldstandardtt/OldStandard-Regular.ttf'},
              'font_bold': {'id': 'font_bold', 'kind': 'font', 'path': 'assets/fonts/oldstandardtt/OldStandard-Bold.ttf'}}
    for key,role in [('text_title','title'),('text_body','body'),('text_ad','advertisement')]:
        assets[key] = {'id':key, 'kind':'text', 'path':'unused.txt', 'metadata':{'role':role}}
    template = {'id':'template_press_v2','kind':'template','path':'assets/template.json',
                'metadata':{'literal_text':['MILLE FEUILLES','Journal de démonstration — Édition synthétique']}}
    assets[template['id']] = template
    context = {'config':{'width':2680,'height':3698,'columns':4,'layout_profile':validation.LAYOUT_PROFILE,
                         'degradation_profile': {'name':'identity'}},
               'options':deepcopy(layout.DEFAULT_OPTIONS),'font':assets['font_regular'],'assets':assets}
    return context, template


def test_exact_font_metrics_and_source_roles_match():
    context, template = fixture_context()
    assert validation._layout_template_errors(REPO, fixture_page(), template, context) == []


@pytest.mark.parametrize('mutate,fragment', [
    (lambda p,c: p['provenance']['parameters']['layout_typography']['main'].update(line_spacing_small=99), 'font metrics'),
    (lambda p,c: p['provenance']['parameters']['layout_typography']['main'].update(small_body_size=29), 'template ratio'),
    (lambda p,c: c['config'].update(columns=5), 'explicit config.columns'),
    (lambda p,c: p['lines'][3]['extensions']['mf:font'].update(size=38), 'source role'),
    (lambda p,c: p['lines'][3]['extensions']['mf:font'].update(asset_id='font_bold'), 'source role'),
])
def test_template_bound_typography_mutations_fail(mutate, fragment):
    context, template = fixture_context()
    page = fixture_page()
    mutate(page,context)
    errors = validation._layout_template_errors(REPO, page, template, context)
    assert any(fragment in error for error in errors), errors


def test_dataset_template_requires_versioned_preset(tmp_path):
    import json
    context, template = fixture_context()
    (tmp_path/'assets').mkdir()
    content = {'id':'template_press_v2','version':'0.3.0','profile':validation.LAYOUT_PROFILE,
               'calibrated':False,'heading':template['metadata']['literal_text'][0],
               'subtitle':template['metadata']['literal_text'][1],'layout_options':deepcopy(layout.DEFAULT_OPTIONS)}
    (tmp_path/'assets/template.json').write_text(json.dumps(content))
    (tmp_path/'config.json').write_text(json.dumps({'render':context['config']}))
    manifest = {'profile':validation.LAYOUT_PROFILE,'config':{'path':'config.json'}}
    result, errors = validation._load_layout_context(tmp_path,manifest,context['assets'])
    assert result and not errors
    content['layout_options']['boxed_ad_probability'] = .9
    (tmp_path/'assets/template.json').write_text(json.dumps(content))
    result, errors = validation._load_layout_context(tmp_path,manifest,context['assets'])
    assert result is None and any('preset version 1' in error for error in errors)


def test_boxed_advertisement_title_is_distinguished_by_source_span():
    page = fixture_page()
    context, template = fixture_context()
    adline = page['lines'][3]
    size = page['articles'][2]['extensions']['mf:layout']['body_font_size']
    adline['extensions']['mf:font'].update(asset_id='font_bold',size=max(12,round(size*1.25)))
    next(span for span in page['provenance']['text_spans'] if span['block_ids']==['ad_block'])['asset_id']='text_title'
    assert validation.validate_page(page) == []
    assert validation._layout_template_errors(REPO,page,template,context) == []


def test_missing_column_rule_is_rejected():
    page = fixture_page()
    missing = page['blocks'].pop()
    page['reading_order']['unordered_block_ids'].remove(missing['id'])
    assert any('planned zone/column rule' in error for error in validation.validate_page(page))


def test_failed_headline_attempt_count_is_consistent():
    page = fixture_page()
    page['provenance']['parameters']['layout_rejected_candidates']['headline'] = 5
    assert any('rejection count' in error for error in validation.validate_page(page))


def test_terminal_rejections_cannot_omit_a_declared_zone():
    page = fixture_page()
    page['provenance']['parameters']['layout_termination_rejections'].pop('rez_de_chaussee')
    assert any('terminal rejection' in error for error in validation.validate_page(page))


def test_invalid_polygon_fails_before_layout_intersections():
    page = fixture_page()
    page['blocks'][-1]['polygon'] = [[94,450],[150,480],[94,480],[150,450]]
    assert validation.validate_page(page)


def plan_for(seed=3, *, rdc=True, headline=True):
    options = deepcopy(layout.DEFAULT_OPTIONS)
    options.update(rez_de_chaussee_probability=int(rdc), headline_probability=int(headline))
    draws = layout.draw_layout(random.Random(seed), options, width=800, height=1100, margin=30,
                               gutter=10, column_ok=lambda _: True)
    return layout.place_zones(draws, top=100, bottom=1060, min_zone_height=60)


@pytest.mark.parametrize('rdc,headline', [(False, False), (False, True), (True, False), (True, True)])
def test_real_planner_outputs_fit_page(rdc, headline):
    for seed in range(20):
        assert validation._check_layout_plan(plan_for(seed, rdc=rdc, headline=headline), width=800, height=1100) == []


@pytest.mark.parametrize('value', [None, [], 0, True, 'plan', {'version': '1'}])
def test_malformed_top_level_is_controlled(value):
    assert validation._check_layout_plan(value, width=800, height=1100)


@pytest.mark.parametrize('mutate', [
    lambda p: p.update(extra=True),
    lambda p: p.pop('rez_de_chaussee_share'),
    lambda p: p.update(version='2'),
    lambda p: p.update(width=799),
    lambda p: p.update(width=True),
    lambda p: p.update(margin=-1),
    lambda p: p.update(margin=10**400),
    lambda p: p.update(gutter=-1),
    lambda p: p.update(gutter=float('nan')),
    lambda p: p.update(min_zone_height=-1),
    lambda p: p.update(min_zone_height=True),
    lambda p: p.update(zones=None),
    lambda p: p['zones'].__setitem__(0, None),
    lambda p: p['zones'][0].update(extra=True),
    lambda p: p['zones'][0]['bbox'].__setitem__(1, -100),
    lambda p: p['zones'][1]['bbox'].__setitem__(3, 1200),
    lambda p: p['zones'][0]['bbox'].append(100),
    lambda p: p['zones'][0]['bbox'].__setitem__(0, float('inf')),
    lambda p: p['zones'][0].update(columns=[[30, 770]], headline_span=None),
    lambda p: p['zones'][0]['columns'][0].__setitem__(1, 80),
    lambda p: p['zones'][0]['columns'][0].append(80),
    lambda p: p['zones'][0].update(headline_span=True),
    lambda p: p['zones'][1].update(headline_span=2),
    lambda p: p.update(rez_de_chaussee_share=float('nan')),
    lambda p: p.update(rez_de_chaussee_share='0.3'),
    lambda p: p.update(rez_de_chaussee_share=0.59),
    lambda p: p.update(zone_rules=[]),
    lambda p: p['zone_rules'][0].__setitem__(0, -100),
    lambda p: p['zone_rules'][0].__setitem__(2, 900),
    lambda p: p['zone_rules'][0].append(10),
    lambda p: p['zone_rules'][0].__setitem__(3, p['zone_rules'][0][3] + 1),
])
def test_falsified_plan_is_rejected(mutate):
    plan = plan_for()
    mutate(plan)
    assert validation._check_layout_plan(plan, width=800, height=1100)


def test_share_cannot_be_declared_for_single_zone():
    plan = plan_for(rdc=False)
    plan['rez_de_chaussee_share'] = 0.3
    assert validation._check_layout_plan(plan, width=800, height=1100)


@pytest.mark.parametrize('width,height', [(True, 1100), (800, 0), (10**400, 1100)])
def test_invalid_page_dimensions_are_controlled(width, height):
    assert validation._check_layout_plan(plan_for(), width=width, height=height)


def remove_text_block(page, bid):
    block = next(block for block in page['blocks'] if block['id'] == bid)
    line_ids = set(block['line_ids'])
    page['blocks'].remove(block)
    for article in page['articles']:
        if bid in article['block_ids']:
            article['block_ids'].remove(bid)
    page['lines'] = [line for line in page['lines'] if line['id'] not in line_ids]
    page['words'] = [word for word in page['words'] if word['line_id'] not in line_ids]
    page['reading_order']['block_ids'].remove(bid)
    page['reading_order']['line_ids'] = [lid for lid in page['reading_order']['line_ids'] if lid not in line_ids]
    page['provenance']['text_spans'] = [span for span in page['provenance']['text_spans'] if bid not in span['block_ids']]


def test_headline_cannot_occupy_only_one_of_its_declared_columns():
    page = fixture_page()
    remove_text_block(page, 'body_second')
    assert any('every spanned column' in error for error in validation.validate_page(page))


def test_headline_body_requires_two_lines_per_column():
    page = fixture_page()
    body = next(block for block in page['blocks'] if block['id'] == 'body_second')
    lid = body['line_ids'].pop()
    page['lines'] = [line for line in page['lines'] if line['id'] != lid]
    page['words'] = [word for word in page['words'] if word['line_id'] != lid]
    page['reading_order']['line_ids'].remove(lid)
    assert any('at least two lines' in error for error in validation.validate_page(page))


def test_ordinary_ad_and_frame_cannot_enter_reserved_body_band():
    page = fixture_page()
    advertisement = next(block for block in page['blocks'] if block['id'] == 'ad_block')
    x0, y0 = advertisement['polygon'][0]
    dx, dy = 500 - x0, 460 - y0
    framing = page['articles'][2]['extensions']['mf:layout']['box']
    selected = [block for block in page['blocks'] if block['id'] in ['ad_block', *framing['rule_ids']]]
    selected += [line for line in page['lines'] if line['block_id'] == 'ad_block']
    selected += [word for word in page['words'] if word['line_id'] in advertisement['line_ids']]
    for item in selected:
        item['polygon'] = [[x + dx, y + dy] for x, y in item['polygon']]
        if 'baseline' in item:
            item['baseline'] = [[x + dx, y + dy] for x, y in item['baseline']]
    box_bounds = framing['bbox']
    framing['bbox'] = [box_bounds[0] + dx, box_bounds[1] + dy, box_bounds[2] + dx, box_bounds[3] + dy]
    assert any('available column' in error for error in validation.validate_page(page))


def test_body_band_can_exceed_actual_ink_envelope_from_common_preparation():
    page = fixture_page(.3, 2)
    page['provenance']['parameters']['layout']['zones'][0]['headline_body_band'][3] += 1
    assert validation.validate_page(page) == []


def test_title_must_really_span_more_than_one_column_and_gutter():
    page = fixture_page()
    for item in page['blocks'] + page['lines'] + page['words']:
        if item['id'] in {'title', 'title_line', 'title_word'}:
            item['polygon'] = rect([94, 350, 400, 420])
            if 'baseline' in item:
                item['baseline'] = [[94, 416], [400, 416]]
    assert any('one column plus gutter' in error for error in validation.validate_page(page))


def test_lower_zone_cannot_enlarge_normal_body_from_its_wider_columns():
    page = fixture_page()
    page['provenance']['parameters']['layout_typography']['rez_de_chaussee']['normal_body_size'] += 1
    assert any('main width/ratio' in error for error in validation.validate_page(page))


def test_body_band_must_leave_one_normal_interline_below():
    page = fixture_page()
    zone = page['provenance']['parameters']['layout']['zones'][0]
    spacing = page['provenance']['parameters']['layout_typography']['main']['line_spacing_normal']
    zone['headline_body_band'][3] = zone['bbox'][3] - spacing + 1
    assert any('one normal interline' in error for error in validation.validate_page(page))


@pytest.mark.parametrize('retained', ['all', 'annotations', 'template'])
def test_relabelling_v2_cannot_bypass_its_semantics(retained):
    page = fixture_page()
    page['profile'] = validation.MEASURED_PROFILE
    if retained != 'all':
        params = page['provenance']['parameters']
        for key in list(params):
            if key.startswith('layout'):
                params.pop(key)
    if retained == 'template':
        for article in page['articles']:
            article.pop('extensions', None)
    assert validation.validate_page(page)


def test_legacy_profile_rejects_v2_template_registry():
    context, _ = fixture_context()
    result, errors = validation._load_layout_context(REPO, {'profile': validation.MEASURED_PROFILE}, context['assets'])
    assert result is None and any('reserved for the v2' in error for error in errors)


def test_legacy_config_cannot_request_layout_v2(tmp_path):
    import json
    (tmp_path / 'config.json').write_text(json.dumps({'render': {'layout_profile': validation.LAYOUT_PROFILE}}))
    manifest = {'profile': 'fr_press_19c_columns_4_6', 'config': {'path': 'config.json'}}
    _, errors = validation._load_degradation_profile(tmp_path, manifest, set())
    assert any('layout_profile differs' in error for error in errors)
