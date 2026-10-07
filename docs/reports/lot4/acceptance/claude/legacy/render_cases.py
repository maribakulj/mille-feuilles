"""Render the six historical compact cases in memory-light mode and print their digests.

Run with PYTHONPATH pointing at an extracted tree (src/, schemas/, assets/) of the commit under
test, or at the repository checkout, through `uv run --locked --offline`.
Arguments: OUTPUT_DIR (new, empty). Prints one JSON object {case: [png_sha256, page_sha256]}.
Cases: degradation clean / mixed / faint × page index 0 / 3, 800×1100, seed 77, default
columns, no degradation profile (original path). The page digest is SHA-256 of the
canonical JSON (sort_keys, compact separators, ensure_ascii False).
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

from mille_feuilles.render import Config, render_page
import mille_feuilles.render as module

out = Path(sys.argv[1])
out.mkdir(parents=True)
# Assets of the commit under test: next to the loaded package (src/../assets).
shutil.copytree(Path(module.__file__).resolve().parents[2] / "assets", out / "assets")
assets = json.loads((out / "assets/catalog.json").read_text(encoding="utf-8"))["assets"]
result = {"render_module": module.__file__}
for mode in ("clean", "mixed", "faint"):
    for index in (0, 3):
        page = render_page(Config(width=800, height=1100, seed=77, degradation=mode), index, assets, out)
        png = hashlib.sha256((out / page["image"]["path"]).read_bytes()).hexdigest()
        canonical = json.dumps(page, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        result[f"{mode}-{index}"] = [png, hashlib.sha256(canonical.encode()).hexdigest()]
print(json.dumps(result, ensure_ascii=False))
