# Comparaison historique du chemin d'origine (sans profil) — RÉSULTAT

Exécutée le 7 octobre 2026 par Claude (w8:p2), après le signal de commit du lot 4 donné par Codex. Aucune
écriture dans le dépôt ; `git status` est resté vide avant et après.

**Portée.** Uniquement le chemin d'origine `--degradation clean|mixed|faint`, sans `degradation_profile`
ni `layout_profile`. Elle est **distincte** de `--legacy-reference` d'`accept_layout.py`, qui couvre le
chemin mesuré non-v2 ; les deux portées ne se fusionnent pas.

**États comparés.**
- `cb24e39e42d6c7519a32f6b70bcbccced6e13f36` : `git archive` de `src schemas assets` dans `ref/` ;
- `69f0e50834e06d9f501411ada2b36f9677ee2a22` (lot 4) : même extraction dans `lot4/` ;
- le checkout courant du dépôt, à ce même commit, propre.

Le module chargé est consigné par `render_module` dans chaque JSON (`ref.json`, `lot4.json`,
`checkout.json`).

**Cas.** 800×1100, graine 77, colonnes libres, clean/mixed/faint × index de page 0 et 3. Les sorties sont
le SHA-256 du PNG et le SHA-256 de la page JSON canonique (sort_keys, séparateurs compacts).
Script : `render_cases.py` (SHA-256 `580e9ab824d28e978fc1f8b0a81092f2af7160c6971b18d3f1de3daaba21118f`). Commandes exactes : `COMMANDES.md`. Environnement :
`uv run --locked --offline`, avec le `uv.lock` du checkout courant.

| Cas | PNG (début du SHA) | Page JSON (début du SHA) | cb24e39 = lot 4 = checkout |
|---|---|---|---|
| clean-0 | `1839f1dcdd2a5ef5…` | `2632d762de2c5ea1…` | oui |
| clean-3 | `a353f875d9298bb4…` | `240abec7bcb7bb39…` | oui |
| mixed-0 | `c16591b9db81f674…` | `8ac9cdf3414f8c10…` | oui |
| mixed-3 | `5db0593e41855121…` | `851d118115811149…` | oui |
| faint-0 | `1a96aab42fbff0e9…` | `5c65c6205751d320…` | oui |
| faint-3 | `3191e545f2160d8b…` | `f9fe399bfdc17f12…` | oui |

**Résultat : 6 cas sur 6 identiques octet pour octet** (PNG et page JSON) entre `cb24e39`, le commit du lot 4
et le checkout.

**Limites.**
- un seul jeu de paramètres (800×1100, graine 77) et deux index ;
- l'environnement Python est celui du checkout courant ;
- rien n'est dit des exports, manifestes, QA ni des autres tailles ;
- le chemin mesuré non-v2 relève de `--legacy-reference`.
