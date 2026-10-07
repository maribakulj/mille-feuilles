"""Mutation check of tests/test_exports_newseye.py (scratchpad only; never touches the repository).

Each mutant is a textual edit of src/mille_feuilles/exports_newseye.py, written to an overlay package
directory OVERLAY/mille_feuilles/ placed first on PYTHONPATH (its __init__ chains to the repository
package). The report schema path is pinned to the repository, because the overlay changes parents[2].
Usage, from the repository root: python mutate_producer.py OVERLAY
"""
import os
import subprocess
import sys
from pathlib import Path

overlay = Path(sys.argv[1])
package = overlay / "mille_feuilles"
package.mkdir(parents=True, exist_ok=True)
(package / "__init__.py").write_text(
    "from pathlib import Path as _P\n"
    "_REPO = _P('/Users/marcel/heritage-synth/src/mille_feuilles')\n"
    "__path__ = [str(_P(__file__).parent), str(_REPO)]\n"
    "exec(compile((_REPO / '__init__.py').read_text(), str(_REPO / '__init__.py'), 'exec'))\n")
src = Path("src/mille_feuilles/exports_newseye.py").read_text(encoding="utf-8").replace(
    '_REPORT_SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "newseye-report.schema.json"',
    '_REPORT_SCHEMA = Path("/Users/marcel/heritage-synth/schemas/newseye-report.schema.json")')


def advert_first(s):
    anchor = '        region = _node(element, "TextRegion", id=f"r_{bid}", type=region_type,'
    s = s.replace(anchor, '        if block["category"] == "annonce":\n'
                          '            _node(_node(element, "AdvertRegion", id=f"a_{bid}"), "Coords", points=text_polygons[bid])\n'
                  + anchor, 1)
    return s.replace('        if block["category"] == "annonce":\n'
                     '            advert = _node(element, "AdvertRegion", id=f"a_{bid}")\n'
                     '            _node(advert, "Coords", points=text_polygons[bid])\n'
                     '            mapping[f"a_{bid}"] = bid',
                     '        if block["category"] == "annonce":\n            mapping[f"a_{bid}"] = bid')


MUTANTS = {
    "témoin (intact)": None,
    "annonce avant son texte": advert_first,
    "index de ligne +1": ('readingOrder {{index:{line_index};}} "', 'readingOrder {{index:{line_index + 1};}} "'),
    "arrondi du banquier": ("        rounded = _rounded(points, page, polygon=polygon)",
                            "        rounded = [[round(x), round(y)] for x, y in points]"),
    "chevauchement non contrôlé": ("            if other != bid and advert.intersection(polygon(points)).area > 0:",
                                   "            if False:"),
    "baseline réduite aux extrémités": ('_points(line["baseline"], page, polygon=False)',
                                        '_points([line["baseline"][0], line["baseline"][-1]], page, polygon=False)'),
    "article du premier bloc partout": ("f\"structure {{id:{block['article_id']}; type:article;}}\")",
                                        "f\"structure {{id:{page['blocks'][0]['article_id']}; type:article;}}\")"),
    "annonce hors de l'ordre": ('        for index, bid in enumerate(order):\n'
                                '            _node(group, "RegionRefIndexed", index=index, regionRef=f"r_{bid}")',
                                '        for index, bid in enumerate([b for b in order if blocks[b]["category"] != "annonce"]):\n'
                                '            _node(group, "RegionRefIndexed", index=index, regionRef=f"r_{bid}")'),
    "bloc libre accepté": ('            raise NewsEyeExportError("free_text_block", f"bloc textuel sans article : {bid}")',
                           '            block = {**block, "article_id": "libre"}'),
    "deux-points accepté": ('or "\\\\" in value or ":" in value', 'or "\\\\" in value'),
    "contrôles U+0000..001F/U+007F acceptés": ("        or any(ord(char) < 32 or ord(char) == 127 for char in value)\n", ""),
    "segments vides et '..' acceptés": ('        or any(p in ("", ".", "..") for p in value.split("/")) or PurePosixPath(value).is_absolute()',
                                        '        or PurePosixPath(value).is_absolute()'),
    "apostrophe normalisée": ('                _text(word_elem, word["text"])',
                              "                _text(word_elem, word[\"text\"].replace(\"’\", \"'\"))"),
}
for name, mutation in MUTANTS.items():
    if mutation is None:
        mutant = src
    elif callable(mutation):
        mutant = mutation(src)
        assert mutant != src, name
    else:
        assert mutation[0] in src, name
        mutant = src.replace(*mutation)
    (package / "exports_newseye.py").write_text(mutant, encoding="utf-8")
    run = subprocess.run(["uv", "run", "--locked", "--offline", "pytest", "-q", "-p", "no:cacheprovider",
                          "tests/test_exports_newseye.py"], env={**os.environ, "PYTHONPATH": str(overlay)},
                         capture_output=True, text=True)
    print(f"{name:34} {run.stdout.strip().splitlines()[-1]}", flush=True)
