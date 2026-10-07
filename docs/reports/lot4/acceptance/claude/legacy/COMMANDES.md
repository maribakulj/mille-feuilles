# Comparaison historique du chemin d'origine (sans profil) — protocole préparé, NON EXÉCUTÉ

Portée : uniquement le chemin d'origine `--degradation clean|mixed|faint`, sans `degradation_profile` ni
`layout_profile`. Six cas compacts : clean, mixed et faint × index de page 0 et 3 ; 800×1100, graine 77,
colonnes libres. Les sorties comparées sont le PNG et la page JSON. Cette preuve est **distincte** de
`--legacy-reference` de `tools/accept_layout.py`, qui couvre le chemin mesuré non-v2 : leurs portées ne
se fusionnent pas.

À exécuter seulement après le signal de commit du lot 4 (`$LOT4` = ce commit). Ordre, depuis
`~/heritage-synth`, avec `D` égal à ce dossier :
```sh
mkdir -p $D/ref $D/lot4
git archive cb24e39 src schemas assets | tar -x -C $D/ref     # lecture seule ; aucune mutation Git
git archive $LOT4 src schemas assets | tar -x -C $D/lot4
PYTHONPATH=$D/ref/src  uv run --locked --offline python $D/render_cases.py $D/out-ref  > $D/ref.json
PYTHONPATH=$D/lot4/src uv run --locked --offline python $D/render_cases.py $D/out-lot4 > $D/lot4.json
uv run --locked --offline python $D/render_cases.py $D/out-checkout > $D/checkout.json   # arbre actuel
```
Comparaison : les six paires (PNG, page) de `ref.json` et `lot4.json` doivent être égales, et
`checkout.json` doit égaler `lot4.json`. `render_module` atteste le code chargé.

Limites :
- les actifs et les schémas sont ceux de chaque commit testé ; l'environnement Python verrouillé est
  celui du checkout courant (`uv.lock`) ;
- un seul jeu de paramètres et deux index ;
- aucune affirmation sur les exports, les manifestes ou d'autres tailles.
