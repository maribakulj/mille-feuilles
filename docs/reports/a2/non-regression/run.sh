#!/bin/sh
# Non-regression without content option: identical commands, code 178a79b vs HEAD.
set -e
S=/private/tmp/claude-501/-Users-marcel/99660c03-830a-4e8e-be3c-f4fdedd08762/scratchpad/a2-historique
PY=/Users/marcel/heritage-synth/.venv/bin/python
OUT=/Users/marcel/heritage-synth/runs/a2-non-regression
mkdir -p $OUT
export PYTHONDONTWRITEBYTECODE=1
COMMON="--pages 2 --width 1200 --height 1656 --dpi 67 --columns 4 --seed 20261007 --jobs 1"
for code in old new; do
  if [ $code = old ]; then ROOTDIR=$S/old-git; else ROOTDIR=/Users/marcel/heritage-synth; fi
  (cd $ROOTDIR && PYTHONPATH=$ROOTDIR/src $PY -m mille_feuilles.cli generate --output $OUT/$code-v2 $COMMON --layout-profile fr_press_19c_layout_v2 --degradation-profile identity > $OUT/$code-v2.json)
  (cd $ROOTDIR && PYTHONPATH=$ROOTDIR/src $PY -m mille_feuilles.cli generate --output $OUT/$code-ancien $COMMON > $OUT/$code-ancien.json)
done
