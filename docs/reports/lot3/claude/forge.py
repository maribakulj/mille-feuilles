# Transcription of the inline check (point d): consistent all-ink mask forgery on a COPY of lot-j1.
import sys, json
from pathlib import Path
import numpy as np
from PIL import Image
from mille_feuilles.io import sha256, write_json
from mille_feuilles.diagnostics import save_mask, document, mask_path, diagnostics_path
from mille_feuilles.exports import export_page, export_coco
from mille_feuilles.validation import validate_dataset
R = Path(sys.argv[1]); pid = "mf_0000"; pj = R / f"pages/{pid}.json"; page = json.loads(pj.read_text())
img = np.asarray(Image.open(R / page["image"]["path"]))
fake = np.ones(img.shape, bool); mh = save_mask(fake, R / mask_path(pid))
rep = document(img, fake, page, image_sha256=page["image"]["sha256"], mask_sha256=mh)
ranks = {"readable": 0, "uncertain": 1, "illegible": 2}
for w in page["words"]: w["legibility"] = rep["words"][w["id"]]["legibility"]
byid = {w["id"]: w for w in page["words"]}
for l in page["lines"]: l["legibility"] = max((byid[i]["legibility"] for i in l["word_ids"]), key=ranks.get)
write_json(R / diagnostics_path(pid), rep)
page["extensions"]["mf:diagnostics"].update(sha256=sha256(R / diagnostics_path(pid)), mask_sha256=mh)
write_json(pj, page); export_page(page, R)
export_coco([json.loads(p.read_text()) for p in sorted((R / "pages").glob("*.json"))], R)
m = json.loads((R / "manifest.json").read_text())
for rec in m["pages"]: rec["sha256"] = sha256(R / rec["path"])
for a in m["artifacts"]: a["sha256"] = sha256(R / a["path"])
write_json(R / "manifest.json", m)
res = validate_dataset(R)
print("(d) faux masque tout-encre : validation", res["status"], rep["page"]["legibility"])
for e in res["errors"][:6]: print("   ", e[:160])
