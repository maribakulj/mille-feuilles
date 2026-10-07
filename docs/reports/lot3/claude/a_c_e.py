# Transcription of the inline check run on 2026-10-07 (revue lot 3, points a, c, e).
import sys, json, shutil
from pathlib import Path
import numpy as np
from PIL import Image
from mille_feuilles.io import ROOT
from mille_feuilles.render import Config, render_page
from mille_feuilles.degrade import load_profile
from mille_feuilles.diagnostics import load_mask, measure, compare
S = Path(sys.argv[1])
def root(name):
    r = S / name; shutil.rmtree(r, ignore_errors=True); shutil.copytree(ROOT / "assets", r / "assets"); return r
assets = json.loads((ROOT / "assets/catalog.json").read_text())["assets"]
base = dict(width=800, height=1100, columns=4, seed=31)
pages = {}
for name, prof in (("identity", load_profile("identity")), ("controlled", load_profile("controlled-v1"))):
    r = root(name); pages[name] = (r, render_page(Config(**base, degradation_profile=prof), 2, assets, r))
def geom(p):
    return ([(w["id"], w["text"], w["polygon"]) for w in p["words"]],
            [(b["id"], b["polygon"]) for b in p["blocks"]], p["reading_order"])
print("(a) même composition identity/controlled :", geom(pages["identity"][1]) == geom(pages["controlled"][1]))
mi = (pages["identity"][0] / "qa/masks/mf_0002.png").read_bytes()
mc = (pages["controlled"][0] / "qa/masks/mf_0002.png").read_bytes()
print("(c) masque identique malgré la dégradation :", mi == mc)
r, p = pages["controlled"]
img = np.asarray(Image.open(r / p["image"]["path"])); mask = load_mask(r / "qa/masks/mf_0002.png", img.shape)
stored = json.loads((r / "qa/diagnostics/mf_0002.json").read_text())
re = measure(img, mask, p); re["inputs"] = stored["inputs"]
print("    recalcul diagnostics = fichier :", compare(stored, re) == [], stored["page"]["legibility"])
print("    étiquettes page = diagnostics :", all(w["legibility"] == stored["words"][w["id"]]["legibility"] for w in p["words"]))
print("(e) page_seed identique entre profils :", pages["identity"][1]["provenance"]["seed"] == pages["controlled"][1]["provenance"]["seed"])
rl = root("legacy"); pl = render_page(Config(**base, degradation="clean"), 2, assets, rl)
print("    composition ancien mode == mesuré (même graine) :", geom(pl) == geom(pages["identity"][1]))
