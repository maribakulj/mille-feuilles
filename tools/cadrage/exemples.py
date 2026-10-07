#!/usr/bin/env python3
"""Exemples réels pour les conventions à valider par Marcel (CADRAGE §6).

Choisit, dans les seules pages **train** de NewsEye AS (et une page train du
manifeste presse E7 d'axel pour `ſ`), une région par convention, puis en
découpe une vignette avec `sips` (macOS) dans un dossier hors dépôt
(`~/heritage-synth-cadrage/exemples/` par défaut). Écrit `exemples.json` :
page, image source, rectangle (px de l'image), vignette.

    python3 tools/cadrage/exemples.py [--out ~/heritage-synth-cadrage/exemples]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import calibrer as C  # noqa: E402


def crop(img: str, box: tuple[float, float, float, float], out: Path, pad: int = 40) -> str:
    x0, y0, x1, y1 = (int(v) for v in box)
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    subprocess.run(["sips", "-c", str(h), str(w), "--cropOffset", str(y0), str(x0),
                    img, "--out", str(out)], check=True, capture_output=True)
    subprocess.run(["sips", "-Z", "1600", str(out)], check=True, capture_output=True)
    return str(out)


def union(polys: list[list[C.Point]]) -> tuple[float, float, float, float]:
    return C.bbox([p for poly in polys for p in poly])


def main() -> int:
    ap = argparse.ArgumentParser()
    home = Path.home()
    ap.add_argument("--as-manifest", default=str(home / "axel/data/prepared/olr/newseye_as.json"))
    ap.add_argument("--e7-pages", default=str(home / "axel/data/prepared/presse_e7/pages.jsonl"))
    ap.add_argument("--out", default=str(home / "heritage-synth-cadrage/exemples"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    m = json.loads(Path(a.as_manifest).read_text(encoding="utf-8"))
    pages = [p for p in m["pages"] if p["split"] == "train"]
    assert all(p["split"] == "train" for p in pages)
    found: dict[str, dict] = {}

    def keep(key: str, p: dict, box: tuple[float, float, float, float], note: str) -> None:
        if key in found:
            return
        f = crop(p["image"], box, out / f"{key}.jpg")
        found[key] = {"page": p["page"], "titre": p["title"], "date": p["date"],
                      "image": p["image"], "rectangle": [round(v) for v in box],
                      "vignette": f, "note": note}

    for p in sorted(pages, key=lambda p: p["page"]):
        if p["epoch"] != "XIXe":
            continue
        pg = C.parse_page(Path(p["xml"]).read_bytes())
        bl = C.type_blocks(pg)
        for b in bl:
            ln = [x for x in b["lines"] if len(x["poly"]) >= 3]
            if b["category"] == "titre" and len(ln) >= 2:
                keep("titre_multiligne", p, C.bbox(b["poly"]), f"titre de {len(ln)} lignes")
            if b["category"] == "annonce" and len(ln) >= 6:
                keep("annonce", p, C.bbox(b["poly"]), f"bloc d'annonce de {len(ln)} lignes")
            if b["category"] == "tableau" and len(ln) >= 6:
                keep("tableau", p, C.bbox(b["poly"]), "bloc typé tableau")
            if b["category"] == "texte":
                for i, x in enumerate(ln[:-1]):
                    t = x["text"].strip()
                    if t.endswith("¬") and len(t) > 25 and "cesure" not in found:
                        keep("cesure", p, union([x["poly"], ln[i + 1]["poly"]]),
                             f"« {t} » / « {ln[i + 1]['text'].strip()} »")
                    if ("« " in t or " ;" in t or " :" in t) and "ponctuation" not in found:
                        keep("ponctuation", p, C.bbox(x["poly"]), f"« {t} »")
        # article qui saute de colonne : deux blocs successifs du même article,
        # le second en haut de la colonne suivante
        by_id = {b["id"]: b for b in bl}
        seq = [by_id[r] for r in pg["order"] if r in by_id and by_id[r]["category"] == "texte"]
        for u, v in zip(seq, seq[1:]):
            au = u["lines"][0]["article"] if u["lines"] else None
            av = v["lines"][0]["article"] if v["lines"] else None
            bu, bv = C.bbox(u["poly"]), C.bbox(v["poly"])
            if (au and au == av and bv[0] > bu[2] - 20 and bv[1] < bu[1]
                    and len(u["lines"]) >= 8 and "saut_de_colonne" not in found
                    and max(bu[3], bv[3]) - min(bu[1], bv[1]) < 0.35 * pg["height"]):
                box = (bu[0], min(bu[1], bv[1]), bv[2], max(bu[3], bv[3]))
                keep("saut_de_colonne", p, box,
                     f"article {au} : fin de colonne puis haut de la colonne suivante")
        seps = [b for b in bl if b["category"] == "separateur"]
        for s in seps:
            x0, y0, x1, y1 = C.bbox(s["poly"])
            if (x1 - x0) > 0.1 * pg["width"] and (y1 - y0) < 30 and "filet" not in found:
                keep("filet", p, (x0, y0 - 250, x1, y1 + 250), "filet horizontal entre deux articles")
    # page entière pour l'ordre de lecture : Le Matin 1886, 5 colonnes (train)
    for p in pages:
        if p["page"] == "18860115_1-0002":
            found["ordre_page"] = {"page": p["page"], "titre": p["title"], "date": p["date"],
                                   "image": p["image"], "vignette": p["image"],
                                   "note": "page entière, 5 colonnes, ordre article par article"}
    # ſ et ligatures : première page train du XVIIIe du manifeste presse E7
    for line in Path(a.e7_pages).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("split") == "train" and str(r.get("date", ""))[:2] == "17" and Path(r["image"]).exists():
            found["s_long"] = {"page": r["page_id"], "titre": r["title"], "date": r["date"],
                               "image": r["image"], "vignette": r["image"],
                               "note": "page de presse du XVIIIe (Wikisource, train d'E7)"}
            break
    (out / "exemples.json").write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    json.dump(found, sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
