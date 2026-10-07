from pathlib import Path
import hashlib, json, math
from PIL import Image, ImageDraw
R=Path('/Users/marcel/heritage-synth/runs/accept-measured-lot3')
V=R/'visual'; V.mkdir(exist_ok=False)
report=json.loads((R/'acceptance.json').read_text())
names=['compact-identity-x1','compact-controlled-v1-x1','compact-identity-x2','compact-controlled-v1-x2','pilot-size-identity-x2','pilot-size-controlled-v1-x2']
board=Image.new('RGB',(1200,1160),'#dedede')
crops=Image.new('RGB',(1200,6*160),'#ededed'); cd=ImageDraw.Draw(crops)
records=[]
for i,name in enumerate(names):
 lot=R/report['lots'][name]['path']
 with Image.open(lot/'qa/severity_00.jpg') as thumb:
  board.paste(thumb.convert('RGB'),((i%3)*400,(i//3)*580))
 bd=ImageDraw.Draw(board);bd.rectangle(((i%3)*400,(i//3)*580,(i%3)*400+400,(i//3)*580+24),fill='white');bd.text(((i%3)*400+6,(i//3)*580+6),name,fill='black')
 page=json.loads((lot/'pages/mf_0000.json').read_text()); diagnostics=json.loads((lot/'qa/diagnostics/mf_0000.json').read_text())
 image=Image.open(lot/'images/mf_0000.png').convert('RGB')
 for j,label in enumerate(('readable','uncertain','illegible')):
  origin=(j*400,i*160); cd.text((origin[0]+5,origin[1]+5),f'{name} / {label}',fill='black')
  ws=[w for w in page['words'] if w['legibility']==label]
  if not ws:
   cd.text((origin[0]+5,origin[1]+30),'No word in this category',fill='gray');continue
  long=[w for w in ws if len(w['text'])>=4]
  candidates=long or ws
  w=min(candidates,key=lambda w:(abs(diagnostics['words'][w['id']]['contrast']-40),w['id']))
  p=w['polygon'];xy=[max(0,math.floor(min(v[0] for v in p))-8),max(0,math.floor(min(v[1] for v in p))-5),min(image.width,math.ceil(max(v[0] for v in p))+8),min(image.height,math.ceil(max(v[1] for v in p))+5)]
  crop=image.crop(xy); crop_name=f'{name}-{label}.png';crop.save(V/crop_name)
  scale=min(3,380/crop.width,85/crop.height)
  zoom=crop.resize((round(crop.width*scale),round(crop.height*scale)),Image.Resampling.NEAREST)
  crops.paste(zoom,(origin[0]+5,origin[1]+35))
  d=diagnostics['words'][w['id']]
  cd.text((origin[0]+5,origin[1]+125),f"{w['text']} | contrast {d['contrast']} | ink {d['ink_pixels']}",fill='black')
  cd.text((origin[0]+5,origin[1]+140),f"retention {d['retention']}",fill='black')
  records.append({'lot':name,'word_id':w['id'],'text':w['text'],'label':label,'crop':crop_name,'source_bbox':xy,'metrics':d,'source_image_sha256':page['image']['sha256']})
board.save(V/'overview.jpg',quality=92);crops.save(V/'word-crops.jpg',quality=96)
(V/'selection.json').write_text(json.dumps({'selection':'Closest contrast to 40 among words >=4 characters for each nonempty label; fallback all words; deterministic ID tie-break','records':records},ensure_ascii=False,indent=2)+'\n')
print('selected crops',len(records)); print('bytes',sum(p.stat().st_size for p in V.iterdir()))
