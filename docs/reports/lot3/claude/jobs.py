# Transcription of the inline check (point e, jobs 1 vs 2).
import sys
from pathlib import Path
from mille_feuilles.render import Config
from mille_feuilles.pipeline import build_dataset, compare_lots
from mille_feuilles.degrade import load_profile
S = Path(sys.argv[1])
cfg = Config(width=800, height=1100, columns=4, seed=5, degradation_profile=load_profile("controlled-v1"))
r1 = build_dataset(S / "lot-j1", cfg, count=2, jobs=1); r2 = build_dataset(S / "lot-j2", cfg, count=2, jobs=2)
c = compare_lots(S / "lot-j1", S / "lot-j2")
print("(e) jobs 1 vs 2 :", r1["status"], r2["status"], "compare", c["status"], c["files_compared"], "fichiers", c["mismatches"][:3])
