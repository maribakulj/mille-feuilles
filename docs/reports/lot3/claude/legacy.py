import sys, json, shutil, hashlib
from pathlib import Path
out=Path(sys.argv[1]); out.mkdir(parents=True)
from mille_feuilles.io import ROOT
from mille_feuilles.render import Config, render_page
import mille_feuilles.render as R
shutil.copytree(Path("/Users/marcel/heritage-synth/assets"), out/"assets")
assets=json.loads((out/"assets/catalog.json").read_text())["assets"]
res={}
for mode in ("clean","mixed","faint"):
    for idx in (0,3):
        p=render_page(Config(width=800,height=1100,seed=77,degradation=mode),idx,assets,out)
        img=hashlib.sha256((out/p["image"]["path"]).read_bytes()).hexdigest()
        res[f"{mode}-{idx}"]=(img, hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest())
print(R.__file__); print(json.dumps(res))
