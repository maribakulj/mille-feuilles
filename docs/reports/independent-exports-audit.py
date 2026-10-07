"""Independent audit: stdlib + lxml only, no Mille Feuilles validation helpers.

Reads completed pilot files; writes the audit report outside the generated lot.
Run again after production with --final to add global COCO/inventory checks.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

BASE = Path(__file__).resolve().parent
LOT = BASE / 'pilot-v0.2-r2'
REPORT = BASE / 'pilot-v0.2-r2-independent-exports.json'
PAGE = 'http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15'
ALTO = 'http://www.loc.gov/standards/alto/ns-v4#'
NS = {'p': PAGE, 'a': ALTO}
CATEGORIES = ['titre', 'texte', 'legende', 'annonce', 'tableau', 'illustration', 'separateur', 'autre']
FAILURES = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def same(actual, expected, label):
    if actual != expected:
        FAILURES.append({'check': label, 'expected': repr(expected)[:400], 'actual': repr(actual)[:400]})


def pts(value):
    return [[float(c) for c in pair.split(',')] for pair in value.split()]


def close(actual, expected, label, tol=1e-7):
    if len(actual) != len(expected) or any(len(a) != 2 or len(b) != 2 or any(not math.isfinite(x) or abs(x-y)>tol for x,y in zip(a,b)) for a,b in zip(actual,expected)):
        FAILURES.append({'check': label, 'expected': expected, 'actual': actual})


def parse(path):
    return etree.parse(str(path), etree.XMLParser(resolve_entities=False, no_network=True))


def audit_page(pid):
    failures_before = len(FAILURES)
    paths = {'canonical': LOT / f'pages/{pid}.json', 'page': LOT / f'exports/page/{pid}.xml', 'alto': LOT / f'exports/alto/{pid}.xml', 'sidecar': LOT / f'exports/reports/{pid}.json'}
    page = read(paths['canonical'])
    pdoc, adoc, sidecar = parse(paths['page']), parse(paths['alto']), read(paths['sidecar'])
    blocks = {b['id']: b for b in page['blocks']}
    lines = {line['id']: line for line in page['lines']}
    words = {w['id']: w for w in page['words']}
    po = pdoc.xpath('//p:ReadingOrder/p:UnorderedGroup/p:OrderedGroup/p:RegionRefIndexed', namespaces=NS)
    same([int(n.get('index')) for n in po], list(range(len(po))), pid + ': PAGE indices')
    same([n.get('regionRef') for n in sorted(po, key=lambda n: int(n.get('index')))], ['b_' + b for b in page['reading_order']['block_ids']], pid + ': PAGE declared block order')
    same(pdoc.xpath('//p:ReadingOrder/p:UnorderedGroup/p:RegionRef/@regionRef', namespaces=NS), ['b_' + b for b in page['reading_order']['unordered_block_ids']], pid + ': PAGE unordered blocks')
    same(adoc.xpath('//a:ReadingOrder/a:OrderedGroup/a:ElementRef/@REF', namespaces=NS), ['b_' + b for b in page['reading_order']['block_ids']], pid + ': ALTO declared block order')
    same(adoc.xpath('//a:ReadingOrder/a:UnorderedGroup/a:ElementRef/@REF', namespaces=NS), ['b_' + b for b in page['reading_order']['unordered_block_ids']], pid + ': ALTO unordered blocks')
    plines = {node.get('id')[2:]: node for node in pdoc.xpath('//p:TextLine', namespaces=NS)}
    alines = {node.get('ID')[2:]: node for node in adoc.xpath('//a:TextLine', namespaces=NS)}
    same(list(plines), page['reading_order']['line_ids'], pid + ': PAGE serialized line order')
    same(list(alines), page['reading_order']['line_ids'], pid + ': ALTO serialized line order')
    tags = {node.get('ID'): node for node in adoc.xpath('//a:Tags/*', namespaces=NS)}
    pregions = {node.get('id')[2:]: node for node in pdoc.xpath('/p:PcGts/p:Page/*[@id]', namespaces=NS) if node.get('id').startswith('b_')}
    ablocks = {node.get('ID')[2:]: node for node in adoc.xpath('//a:PrintSpace/*[@ID]', namespaces=NS)}
    same(set(pregions), set(blocks), pid + ': PAGE block identifiers')
    same(set(ablocks), set(blocks), pid + ': ALTO block identifiers')
    ptexts, atexts, hyps = {}, {}, defaultdict(list)
    special_char_counts = Counter()

    def attrs(node, kind):
        return [tags[ref] for ref in node.get('TAGREFS', '').split() if tags[ref].get('TYPE') == 'mille-feuilles:' + kind]

    for bid, block in blocks.items():
        region, ablock = pregions[bid], ablocks[bid]
        meta = json.loads(region.get('custom'))
        same(meta['category'], block['category'], pid + ': PAGE category ' + bid)
        same(meta['article_id'], block['article_id'], pid + ': PAGE article ' + bid)
        same([tag.get('LABEL') for tag in attrs(ablock,'category')], [block['category']], pid + ': ALTO category ' + bid)
        same([tag.get('LABEL') for tag in attrs(ablock,'article')], [block['article_id']] if block['article_id'] else [], pid + ': ALTO article ' + bid)
        native_kind = {'titre':'TextRegion','texte':'TextRegion','legende':'TextRegion','autre':'TextRegion','annonce':'AdvertRegion','tableau':'TableRegion','illustration':'GraphicRegion','separateur':'SeparatorRegion'}[block['category']]
        same(etree.QName(region).localname,native_kind,pid + ': PAGE region kind ' + bid)
        same([n.get('id')[2:] for n in region.xpath('.//p:TextLine', namespaces=NS)], block['line_ids'],pid + ': PAGE line parent ' + bid)
        same([n.get('ID')[2:] for n in ablock.xpath('./a:TextLine', namespaces=NS)], block['line_ids'],pid + ': ALTO line parent ' + bid)
        expected = [[min(page['image']['width' if axis==0 else 'height'],max(0,math.floor(coord+0.5))) for axis,coord in enumerate(point)] for point in block['polygon']]
        close(pts(region.find('p:Coords',NS).get('points')),expected,pid+': PAGE block polygon '+bid)
        close(pts(ablock.find('a:Shape/a:Polygon',NS).get('POINTS')),block['polygon'],pid+': ALTO block polygon '+bid)

    for lid in page['reading_order']['line_ids']:
        line, pnode, anode = lines[lid], plines[lid], alines[lid]
        ptexts[lid] = pnode.findtext('p:TextEquiv/p:Unicode', namespaces=NS)
        same(ptexts[lid],line['text'],pid + ': PAGE line text '+lid)
        pwords = pnode.findall('p:Word',NS)
        astrings = anode.findall('a:String',NS)
        same([n.get('id')[2:] for n in pwords],line['word_ids'],pid + ': PAGE word order '+lid)
        same([n.get('ID')[2:] for n in astrings],line['word_ids'],pid + ': ALTO word order '+lid)
        spacing_tags = attrs(anode,'spaces')
        gaps = json.loads(spacing_tags[0].get('DESCRIPTION')) if spacing_tags else None
        pieces=[]
        for index,(pword,astring,wid) in enumerate(zip(pwords,astrings,line['word_ids'])):
            word=words[wid]
            same(pword.findtext('p:TextEquiv/p:Unicode',namespaces=NS),word['text'],pid + ': PAGE word text '+wid)
            same(astring.get('CONTENT'),word['text'],pid + ': ALTO word text '+wid)
            custom=json.loads(pword.get('custom'))
            same(custom['char_span'],word['char_span'],pid + ': PAGE Unicode span '+wid)
            same(custom['hyphenation'],word['hyphenation'],pid + ': PAGE hyphenation '+wid)
            start,end=word['char_span'];same(line['text'][start:end],word['text'],pid + ': canonical span '+wid)
            pieces.append(astring.get('CONTENT'))
            if index+1<len(astrings):
                sibling=astring.getnext(); space_present=sibling is not None and etree.QName(sibling).localname=='SP'
                count=gaps[index] if gaps is not None else (1 if space_present else 0)
                same(space_present,count>0,pid + ': ALTO explicit space '+wid)
                pieces.append(' '*count)
            hyp=word['hyphenation']
            if hyp:
                same(astring.get('SUBS_TYPE'),'HypPart1' if hyp['part']=='start' else 'HypPart2',pid + ': ALTO césure part '+wid)
                same(astring.get('SUBS_CONTENT'),hyp['reconstructed_text'],pid + ': ALTO césure reconstruction '+wid)
                same([tag.get('LABEL') for tag in attrs(astring,'hyphenation')],[hyp['group_id']],pid + ': ALTO césure group '+wid)
                hyps[hyp['group_id']].append({'word_id':wid,'line_id':lid,'block_id':line['block_id'],'part':hyp['part'],'text':astring.get('CONTENT'),'reconstructed_text':astring.get('SUBS_CONTENT')})
            else:
                same(astring.get('SUBS_TYPE'),None,pid + ': no invented césure '+wid)
        atexts[lid]=''.join(pieces)
        same(atexts[lid],line['text'],pid + ': ALTO reconstructed line '+lid)
        special_char_counts.update(c for c in line['text'] if ord(c)>127)

    cross_block=[]
    for group,members in hyps.items():
        same([m['part'] for m in members],['start','end'],pid+': césure pairing '+group)
        same(len({m['reconstructed_text'] for m in members}),1,pid+': paired ALTO reconstruction '+group)
        ranks=[page['reading_order']['line_ids'].index(m['line_id']) for m in members]
        same(ranks[1]-ranks[0],1,pid+': consecutive césure lines '+group)
        if len({m['block_id'] for m in members})>1:
            cross_block.append({'group_id':group,'members':members})

    expected_text='\n'.join(lines[lid]['text'] for lid in page['reading_order']['line_ids'])
    page_text='\n'.join(ptexts[lid] for bid in [n.get('regionRef')[2:] for n in sorted(po,key=lambda n:int(n.get('index')))] for lid in blocks[bid]['line_ids'])
    alto_order=[ref[2:] for ref in adoc.xpath('//a:ReadingOrder/a:OrderedGroup/a:ElementRef/@REF',namespaces=NS)]
    alto_text='\n'.join(atexts[lid] for bid in alto_order for lid in blocks[bid]['line_ids'])
    same(page_text,expected_text,pid+': PAGE whole-page transcription')
    same(alto_text,expected_text,pid+': ALTO whole-page transcription')
    article_node=pdoc.find("p:Metadata/p:UserDefined/p:UserAttribute[@name='mille-feuilles:articles']",NS)
    same(json.loads(article_node.get('value')),page['articles'],pid+': PAGE article structure')
    article_tags=[{'id':tag.get('LABEL'),**json.loads(tag.get('DESCRIPTION'))} for tag in tags.values() if tag.get('TYPE')=='mille-feuilles:article']
    same(article_tags,page['articles'],pid+': ALTO article structure')
    same(sidecar['id_mapping'],{prefix+item['id']:item['id'] for collection,prefix in [('blocks','b_'),('lines','l_'),('words','w_')] for item in page[collection]},pid+': sidecar identifier mapping')
    same(sidecar['articles'],page['articles'],pid+': sidecar articles')
    same(sidecar['page_container_mapping'],{'c_'+b['id']:b['id'] for b in page['blocks'] if b['category'] in ('annonce','tableau') and b['line_ids']},pid+': sidecar containers')
    for kind in ('page','alto','coco'):
        if not sidecar.get('not_represented',{}).get(kind):FAILURES.append({'check':pid+': missing loss declaration '+kind})
    same(sidecar['canonical_path'],f'pages/{pid}.json',pid+': sidecar canonical path')
    for kind in ('page','alto'):
        same(sidecar['paths'][kind],str(paths[kind].relative_to(LOT)),pid+': sidecar path '+kind)

    line_ids=page['reading_order']['line_ids']
    selected=list(dict.fromkeys([line_ids[i] for i in (0,1,len(line_ids)//4,len(line_ids)//2,3*len(line_ids)//4,len(line_ids)-1)]+[m['line_id'] for g in cross_block for m in g['members']]))
    examples=[]
    for lid in selected:
        line=lines[lid];pnode=plines[lid];anode=alines[lid]
        for field,tag in [('polygon','Coords'),('baseline','Baseline')]:
            expected=[[math.floor(v+0.5) for v in point] for point in line[field]]
            close(pts(pnode.find('p:'+tag,NS).get('points')),expected,pid+': PAGE sampled '+field+' '+lid)
        apolygon=pts(anode.find('a:Shape/a:Polygon',NS).get('POINTS'));abaseline=pts(anode.get('BASELINE'))
        close(apolygon,line['polygon'],pid+': ALTO sampled line polygon '+lid)
        close(abaseline,line['baseline'],pid+': ALTO sampled baseline '+lid)
        if len(examples)<3 or any(m['line_id']==lid for g in cross_block for m in g['members']):
            examples.append({'line_id':lid,'text':line['text'],'canonical_baseline':line['baseline'],'page_baseline':pts(pnode.find('p:Baseline',NS).get('points')),'alto_baseline':abaseline,'canonical_polygon':line['polygon'],'page_polygon':pts(pnode.find('p:Coords',NS).get('points'))})
    params=page['provenance']['parameters']
    return {'page_id':pid,'status':'pass' if len(FAILURES)==failures_before else 'fail','columns':params['columns'],'degradation':params['degradation'],'angle_degrees':params['angle_degrees'],'counts':{'blocks':len(blocks),'lines':len(lines),'words':len(words),'hyphenation_groups':len(hyps),'cross_block_hyphenations':len(cross_block),'sampled_line_geometries':len(selected)},'categories':dict(Counter(b['category'] for b in blocks.values())),'non_ascii_characters':dict(special_char_counts),'transcription_sha256':hashlib.sha256(expected_text.encode()).hexdigest(),'checked_all_line_and_word_texts':True,'checked_declared_and_serialized_reading_order':True,'checked_all_block_polygons':True,'input_sha256':{key:sha(path) for key,path in paths.items()},'cross_block_examples':cross_block,'other_hyphenation_examples':list(hyps.values())[:2],'geometry_examples':examples}


def audit_global():
    """Independently join the COCO/mapping tables to all canonical blocks."""
    before=len(FAILURES)
    manifest_path=LOT/'manifest.json'
    manifest=read(manifest_path)
    same(manifest['generator']['commit'],'0d1e2b701e9f6ba4d571a5f4894bd40071792225','manifest generation commit')
    same(manifest['generator']['dirty'],False,'manifest clean source tree')
    records=manifest['pages']
    same(len(records),100,'manifest page count')
    same(len({r['id'] for r in records}),100,'unique canonical page identifiers')
    artifact_paths=[item['path'] for item in manifest['artifacts']]
    same(len(artifact_paths),len(set(artifact_paths)),'unique artifact paths')
    actual_files={str(path.relative_to(LOT)) for path in LOT.rglob('*') if path.is_file()}
    indexed=set(artifact_paths)
    same(actual_files-indexed-{'manifest.json','qa/report.json'},set(),'unindexed lot files')
    same(indexed-actual_files,set(),'missing indexed artifacts')
    same(indexed & {'manifest.json','qa/report.json'},set(),'manifest/report excluded from circular inventory')
    fingerprints=[]
    bytes_checked=0
    for item in manifest['artifacts']:
        relative=Path(item['path'])
        same(relative.is_absolute() or '..' in relative.parts,False,'safe artifact path '+str(relative))
        path=LOT/relative
        path.resolve().relative_to(LOT.resolve())
        digest=sha(path)
        same(digest,item['sha256'],'artifact SHA-256 '+str(relative))
        fingerprints.append(str(relative)+' '+digest)
        bytes_checked+=path.stat().st_size
    for item in records:
        same(sha(LOT/item['path']),item['sha256'],'canonical page SHA-256 '+item['id'])
        pid=item['id']
        for relative in (item['path'],f'images/{pid}.png',f'exports/page/{pid}.xml',f'exports/alto/{pid}.xml',f'exports/reports/{pid}.json',f'qa/{pid}.png'):
            same(relative in indexed,True,'required page artifact '+relative)
    same('exports/coco/instances.json' in indexed,True,'required COCO artifact')
    refs=[(manifest['config']['path'],manifest['config']['sha256']),(manifest['assets']['path'],manifest['assets']['sha256']),(manifest['generator']['environment_path'],manifest['generator']['environment_sha256']),(manifest['calibration']['protocol_path'],manifest['calibration']['protocol_sha256']),(manifest['calibration']['files_read']['path'],manifest['calibration']['files_read']['sha256'])]
    for relative,expected_sha in refs:
        same(sha(LOT/relative),expected_sha,'manifest top-level reference SHA-256 '+relative)
    inventory={'status':'pass' if len(FAILURES)==before else 'fail','manifest_sha256':sha(manifest_path),'artifact_files_checked':len(artifact_paths),'artifact_bytes_checked':bytes_checked,'canonical_page_refs_checked':len(records),'top_level_refs_checked':len(refs),'sha256_of_sorted_path_hash_inventory':hashlib.sha256('\n'.join(sorted(fingerprints)).encode()).hexdigest(),'exceptions':['manifest.json: cannot hash itself','qa/report.json: root validation writes it after the frozen inventory; independently excluded by contract'],'expected_generation_commit':manifest['generator']['commit'],'dirty':manifest['generator']['dirty']}

    before=len(FAILURES)
    coco_path=LOT/'exports/coco/instances.json'
    coco=read(coco_path)
    same(coco['categories'],[{'id':i+1,'name':name} for i,name in enumerate(CATEGORIES)],'COCO fixed category table')
    mapping=coco['mille_feuilles_id_mapping']
    same(len(coco['images']),100,'COCO image count')
    same(len(coco['annotations']),17332,'COCO annotation count')
    same(all(type(i['id']) is int for i in coco['images']),True,'COCO integer image IDs')
    same(all(type(a['id']) is int for a in coco['annotations']),True,'COCO integer annotation IDs')
    same(sorted(i['id'] for i in coco['images']),list(range(1,101)),'COCO unique image ID range')
    same(sorted(a['id'] for a in coco['annotations']),list(range(1,17333)),'COCO unique annotation ID range')
    same(set(mapping['images']),{str(i['id']) for i in coco['images']},'COCO complete image ID mapping')
    same(set(mapping['annotations']),{str(a['id']) for a in coco['annotations']},'COCO complete annotation ID mapping')
    images_by_page={mapping['images'][str(item['id'])]:item for item in coco['images']}
    annotations_by_canonical={}
    for annotation in coco['annotations']:
        ref=mapping['annotations'][str(annotation['id'])]
        key=(ref['page_id'],ref['block_id'])
        same(key not in annotations_by_canonical,True,'COCO one annotation per canonical block '+repr(key))
        annotations_by_canonical[key]=annotation
    seen_blocks=set()
    categories=Counter(); columns=Counter();degradations=Counter()
    total_lines=0;total_words=0;max_area_delta=0.0
    for record in records:
        page=read(LOT/record['path']);pid=page['page_id']
        image=images_by_page[pid]
        same(image['file_name'],page['image']['path'],'COCO image path '+pid)
        same([image['width'],image['height']],[page['image']['width'],page['image']['height']],'COCO image dimensions '+pid)
        columns[str(page['provenance']['parameters']['columns'])]+=1
        degradations[page['provenance']['parameters']['degradation']]+=1
        total_lines+=len(page['lines']);total_words+=len(page['words'])
        for block in page['blocks']:
            key=(pid,block['id']);seen_blocks.add(key)
            annotation=annotations_by_canonical[key]
            same(annotation['image_id'],image['id'],'COCO parent image '+repr(key))
            same(annotation['category_id'],CATEGORIES.index(block['category'])+1,'COCO category '+repr(key))
            categories[block['category']]+=1
            coordinates=block['polygon'];flattened=[coordinate for vertex in coordinates for coordinate in vertex]
            same(annotation['segmentation'],[flattened],'COCO polygon '+repr(key))
            xs=[point[0] for point in coordinates];ys=[point[1] for point in coordinates]
            bounds=[min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)]
            same(annotation['bbox'],bounds,'COCO bounding box '+repr(key))
            # Compute shoelace as separate cross-term sums, independent of the
            # generator's export implementation and its helpers.
            n=len(coordinates)
            area=(sum(xs[i]*ys[(i+1)%n] for i in range(n))-sum(ys[i]*xs[(i+1)%n] for i in range(n)))/2
            delta=abs(annotation['area']-area)
            max_area_delta=max(max_area_delta,delta)
            same(area>0 and math.isfinite(annotation['area']) and math.isclose(annotation['area'],area,rel_tol=1e-10,abs_tol=1e-5),True,'COCO polygon area '+repr(key))
            same(annotation['iscrowd'],0,'COCO crowd flag '+repr(key))
    same(set(images_by_page),{r['id'] for r in records},'COCO canonical image coverage')
    same(set(annotations_by_canonical),seen_blocks,'COCO canonical block coverage')
    same(len(seen_blocks),17332,'canonical block count')
    same(dict(columns),{'4':7,'5':33,'6':60},'canonical column distribution')
    declared=read(LOT/'qa/statistics.json')
    for key,value in {'pages':len(records),'blocks':len(seen_blocks),'lines':total_lines,'words':total_words,'categories':dict(categories),'columns':dict(columns),'degradations':dict(degradations)}.items():
        same(declared[key],value,'statistics '+key)
    coco_result={'status':'pass' if len(FAILURES)==before else 'fail','sha256':sha(coco_path),'images_checked':len(coco['images']),'blocks_checked':len(coco['annotations']),'canonical_words_counted':total_words,'canonical_lines_counted':total_lines,'columns':dict(columns),'degradations':dict(degradations),'categories':dict(categories),'declared_category_table':CATEGORIES,'max_polygon_area_delta_px2':max_area_delta,'checks':['Unique integer IDs and exhaustive canonical mappings','Every image filename and dimensions','Every block parent image and category','Every polygon, bbox, area and crowd flag','Canonical totals and column/mode distribution against qa/statistics.json'],'limits':['COCO contains blocks only; text and reading order are covered by the independent seven-page XML sample.','No complete re-execution of the project validators or source corpus reads.']}
    return inventory,coco_result


log_bytes=(BASE/'pilot-v0.2-r2-progress.log').read_bytes()
complete=re.findall(r'pages : (mf_\d+),',log_bytes.decode())
selected=['mf_0004','mf_0001','mf_0005','mf_0009','mf_0013','mf_0036','mf_0029']
same(set(selected).issubset(set(complete)),True,'only completion-journal pages may be audited')
results=[audit_page(pid) for pid in selected]
separator_checks=[]
for pid in selected:
    data=read(LOT/f'pages/{pid}.json')
    xml=parse(LOT/f'exports/page/{pid}.xml')
    matrix=next((t['geometry']['matrix'] for t in data['transforms'] if isinstance(t['geometry'],dict)),None)
    count=0
    for block in data['blocks']:
        if block['category']!='separateur':continue
        count+=1
        node=xml.xpath('//p:SeparatorRegion[@id=$identity]/p:Coords',namespaces=NS,identity='b_'+block['id'])[0]
        rounded=pts(node.get('points'))
        distinct=len(set(map(tuple,rounded)))
        area=sum(x1*y2-x2*y1 for (x1,y1),(x2,y2) in zip(rounded,rounded[1:]+rounded[:1]))/2
        same(distinct,len(rounded),pid+': distinct rounded separator vertices '+block['id'])
        same(area>0,True,pid+': positive rounded separator area '+block['id'])
        thickness=min(math.dist(a,b) for a,b in zip(block['polygon'],block['polygon'][1:]+block['polygon'][:1]))
        same(thickness>=2-1e-5,True,pid+': canonical separator thickness >= 2 px '+block['id'])
        if block['id']=='mf_0029_b0126':
            separator_regression={'page_id':pid,'block_id':block['id'],'status':'pass' if distinct==len(rounded) and area>0 and thickness>=2-1e-5 else 'fail','canonical_polygon':block['polygon'],'page_polygon':rounded,'canonical_thickness_px':thickness,'page_area_px2':area,'page_distinct_vertices':distinct,'rotation_matrix':matrix}
    separator_checks.append({'page_id':pid,'separators_checked':count})
report={'audit_version':'2','audit_time_utc':datetime.now(timezone.utc).isoformat(),'status':'partial_pass' if not FAILURES else 'fail','scope':'Independent native XML rereading on completed sample; no Mille Feuilles validator/reader used. Generated lot is read-only.','lot':'runs/pilot-v0.2-r2','script_sha256':sha(Path(__file__)),'progress_log_snapshot_sha256':hashlib.sha256(log_bytes).hexdigest(),'completed_pages_at_snapshot':len(complete),'sample_page_ids':selected,'sample':results,'totals':{key:sum(page['counts'][key] for page in results) for key in results[0]['counts']},'coverage':{'degradations':sorted({p['degradation'] for p in results}),'columns':sorted({p['columns'] for p in results}),'four_column_note':'included' if any(p['columns']==4 for p in results) else 'No completed 4-column page at the sample snapshot; add one at final audit.'},'coco_global':{'status':'not_run','reason':'Pending complete lot and root coordinator signal.'},'manifest_inventory':{'status':'not_run','reason':'Pending complete lot and root coordinator signal.'},'failures':FAILURES}
if '--final' in sys.argv:
    same(len(complete),100,'all 100 pages complete before final independent audit')
    inventory,coco_result=audit_global()
    report['manifest_inventory']=inventory
    report['coco_global']=coco_result
    report['status']='pass' if not FAILURES else 'fail'
    report['audit_phase']='final'
else:
    report['audit_phase']='sample_only'
report['generation_commit_expected']='0d1e2b701e9f6ba4d571a5f4894bd40071792225'
report['input_sha256']={'config.json':sha(LOT/'config.json'),'environment.json':sha(LOT/'environment.json')}
report['separator_regression']=separator_regression
report['separator_sample_checks']=separator_checks
report['scope']='Fresh independent audit of corrected r2 only, stdlib + lxml. No prior audit status reused, no Mille Feuilles validator/reader used; generated lot read-only.'
REPORT.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'sample_page_ids':selected,'totals':report['totals'],'coverage':report['coverage'],'failures':FAILURES},ensure_ascii=False))
