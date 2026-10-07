"""Create bounded review views from existing acceptance pages; never alter sources."""
import json
from pathlib import Path
from PIL import Image, ImageDraw
from mille_feuilles.io import sha256, write_json

root = Path(__file__).parent / 'accept-layout-v2'
out = root / 'visual'
out.mkdir(exist_ok=False)
report = json.loads((root / 'acceptance.json').read_text())
selected = []
thumbs = []
for name, entry in report['lots'].items():
    if name.startswith('replay'):
        continue
    lot = root / entry['path']
    for page_path in sorted((lot / 'pages').glob('*.json')):
        page = json.loads(page_path.read_text())
        source = lot / page['image']['path']
        with Image.open(source) as original:
            view = original.convert('RGB')
            thumb = view.copy()
            thumb.thumbnail((500, 690))
            thumbs.append((name + '/' + page['page_id'], thumb))
            if name == 'compact-identity-x1':
                continue
            features = []
            blocks = {b['id']: b for b in page['blocks']}
            for kind in ('headline', 'box', 'small_body'):
                article = next((a for a in page['articles'] if a.get('extensions', {}).get('mf:layout', {}).get(kind)), None)
                if article:
                    ids = article['block_ids']
                    if kind == 'small_body':
                        ids = [bid for bid in ids if blocks[bid]['category'] != 'titre'][:1]
                    features.append((kind, [p for bid in ids for p in blocks[bid]['polygon']]))
            lower = next((a for a in page['articles'] if a.get('extensions', {}).get('mf:layout', {}).get('zone_id') == 'rez_de_chaussee'), None)
            if lower:
                features.append(('lower_zone', [p for bid in lower['block_ids'] for p in blocks[bid]['polygon']]))
            for kind, points in features:
                bounds = (max(0, int(min(p[0] for p in points)) - 12),
                          max(0, int(min(p[1] for p in points)) - 12),
                          min(view.width, int(max(p[0] for p in points)) + 13),
                          min(view.height, int(max(p[1] for p in points)) + 13))
                path = out / f'{name}-{page["page_id"]}-{kind}.png'
                view.crop(bounds).save(path)
                selected.append({'path': str(path.relative_to(root)), 'source': str(source.relative_to(root)),
                                 'source_sha256': sha256(source), 'feature': kind,
                                 'crop_box': bounds, 'scale': 1, 'sha256': sha256(path)})
canvas = Image.new('RGB', (1530, 3 * 725), 'white')
draw = ImageDraw.Draw(canvas)
for i, (label, thumb) in enumerate(thumbs):
    x, y = (i % 3) * 510, (i // 3) * 725
    draw.text((x + 4, y + 4), label, fill='black')
    canvas.paste(thumb, (x, y + 24))
canvas.save(out / 'overview.jpg', quality=90)
write_json(out / 'selection.json', {'scope': 'Seven base-page thumbnails and native-size feature crops; no transcription or label accuracy estimate',
                                  'overview': {'path': 'visual/overview.jpg', 'pages': [x[0] for x in thumbs]},
                                  'crops': selected})
print(json.dumps({'pages': len(thumbs), 'crops': len(selected)}))
