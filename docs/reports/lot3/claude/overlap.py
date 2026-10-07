import sys, json, shutil, time
from copy import deepcopy
from pathlib import Path
from mille_feuilles.io import ROOT
from mille_feuilles.render import Config, render_page
from mille_feuilles.degrade import load_profile
S=Path(sys.argv[1]); w,h,label=int(sys.argv[2]),int(sys.argv[3]),sys.argv[4]
assets=json.loads((ROOT/"assets/catalog.json").read_text())["assets"]
def overlaps(p):
    lines={}
    for x in p["words"]: lines.setdefault(x["line_id"],[]).append(x)
    n=over=0; worst=0
    for ws in lines.values():
        for a,b in zip(ws,ws[1:]):
            n+=1; ax=max(q[0] for q in a["polygon"]); bx=min(q[0] for q in b["polygon"])
            if ax>bx: over+=1; worst=max(worst,ax-bx)
    return n,over,round(worst,2)
for f in (1,2):
    prof=deepcopy(load_profile("identity")); prof["oversampling"]=f
    r=S/f"z{f}"; shutil.rmtree(r,ignore_errors=True); shutil.copytree(ROOT/"assets",r/"assets")
    t=time.time(); p=render_page(Config(width=w,height=h,seed=31,columns=(4 if w<1000 else None),degradation_profile=prof),2,assets,r)
    print(f"{label} x{f}: corps {p['provenance']['parameters']['body_font_size']} | paires voisines (n, chevauchantes, pire px) {overlaps(p)} | {time.time()-t:.1f} s", flush=True)
    shutil.rmtree(r)
