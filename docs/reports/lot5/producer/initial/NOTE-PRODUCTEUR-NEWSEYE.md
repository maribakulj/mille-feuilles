# Preuve du producteur `page-newseye-v1` (lot 5) — Claude, w8:p2

Le 7 octobre 2026, à HEAD `7c88927 Verify strict independent NewsEye reader before implementing producer`, avec les fichiers du producteur non commités : les trois fichiers
exclusifs de Claude, figés pendant l'intégration de Codex. Aucune commande Git en écriture ; aucun rendu ;
aucun corpus réel.

## Empreintes (SHA-256)
```
7efdc853c5a3707a86fcf0a62e09c656ccbd067835cfbf946f38fd5a16e46ee6  src/mille_feuilles/exports_newseye.py
dc437904f9b334fbc18e074cd0a09fa569932c9a67c30cdeb7e8b669e9a8961f  tests/test_exports_newseye.py
65534db425aef3a52ef05031bf6a6f793753e16b25b7b77c0394b97655cd5111  docs/EXPORT_NEWSEYE.md
4b9312c9631dfc30cfca78dc2de5c9ed81d159554ff05e8fce478e48df157be6  src/mille_feuilles/newseye_reader.py
350bb98335c33e305a073296146d3aef6eecafc1f7eb5be2c40d15cada4758ff  tests/test_newseye_reader.py
e0b8767e23e7f06bca69538f14812eacee4970db377cba683a85c2f2c8610f55  schemas/newseye-report.schema.json
```

## Commandes et sorties (depuis `~/heritage-synth`)
```sh
uv run --locked --offline pytest -q -p no:cacheprovider tests/test_exports_newseye.py tests/test_newseye_reader.py
# -> pytest-159.txt : « 159 passed » (41 producteur + 118 lecteur)
uv run --locked --offline pytest -p no:cacheprovider tests/test_exports_newseye.py -k real_page -v
# -> pytest-pages-reelles.txt : 3 PASSED (sondes locales FACULTATIVES ; ignorées si runs/ est absent)
uv run --locked --offline ruff check src/mille_feuilles/exports_newseye.py tests/test_exports_newseye.py
# -> ruff.txt : « All checks passed! »
uv run --locked --offline python <dossier>/mutate_producer.py <dossier>/overlay
# -> mutations.txt
```

## Pages réelles (sondes locales facultatives, `runs/` non versionné)
La lecture indépendante (`newseye_reader.read_page`) de chaque projection a été comparée **au canonique**
par `test_real_page_reading_equals_the_canonical_page` :
- ordre ;
- catégories ;
- rangs des annonces ;
- article et texte de chaque ligne ;
- texte et chaque point de chaque mot, ligne, baseline et région (arrondi `floor(v + 0,5)` réécrit dans
  le test depuis le § 5 de la spécification).

Résultat : **PASS** pour les trois pages. Les valeurs observées et les SHA-256 des pages sources et des XML
projetés figurent dans `pages-reelles.json`.

| Page | TextRegion | titres | annonces | rangs des annonces | lignes avec article | mots | filets | SHA du XML |
|---|---:|---:|---:|---|---:|---:|---:|---|
| `pilot-v0.2-r2/pages/mf_0003.json` | 89 | 26 | 14 | [3, 4, 24, 32, 33, 34, 35, 36, 37, 40, 73, 75, 78, 81] | 535 | 3732 | 62 | `f041ef31cd722dd8…` |
| `accept-layout-v2/lots/compact-identity-x1/pages/mf_0001.json` | 64 | 19 | 10 | [6, 7, 8, 13, 22, 26, 27, 34, 35, 39] | 333 | 2402 | 11 | `7966dcc57d63c63b…` |
| `accept-layout-v2/lots/compact-identity-x1/pages/mf_0000.json` | 60 | 16 | 12 | [17, 21, 32, 33, 34, 40, 41, 45, 48, 49, 52, 53] | 365 | 2387 | 8 | `1afefb7560a75162…` |

Pour `pilot-v0.2-r2/mf_0003`, l'export générique lu par le lecteur d'Axel ne montrait aucun titre, aucune
ligne avec article et les annonces en fin d'ordre (C1). La projection `page-newseye-v1`, lue par le lecteur
indépendant de notre profil, retrouve 26 titres, 535 lignes avec article et 14 annonces aux rangs
canoniques. **Portée** : c'est la lecture de notre profil, et non celle du lecteur d'Axel, qui n'a pas été
exécuté (laissé à sa coordination).

## Mutation du producteur (`mutate_producer.py`, dossier temporaire uniquement)
```
témoin (intact)                    41 passed in 1.17s
annonce avant son texte            1 failed, 40 passed in 1.04s
index de ligne +1                  13 failed, 28 passed in 0.65s
arrondi du banquier                5 failed, 36 passed in 0.98s
chevauchement non contrôlé         1 failed, 40 passed in 1.00s
baseline réduite aux extrémités    3 failed, 38 passed in 1.07s
article du premier bloc partout    5 failed, 36 passed in 1.04s
annonce hors de l'ordre            8 failed, 33 passed in 1.08s
bloc libre accepté                 2 failed, 39 passed in 1.03s
chemin d'image non contrôlé        6 failed, 35 passed in 1.07s
apostrophe normalisée              8 failed, 33 passed in 0.62s
```
Le témoin intact donne 41 tests passants ; les 10 mutants sont tous détectés. « Annonce avant son texte »
n'est détecté que par la comparaison au XML attendu, ce qui est voulu : le lecteur ne dépend pas de
l'ordre du document.

## Limites
- Les sondes de pages réelles dépendent de lots locaux non versionnés. La preuve portable est celle des
  fixtures ; la preuve reproductible sur sources ancrées relève de la campagne CLI de Codex.
- Les mutants sont 10 éditions choisies à la main, et non une mutation exhaustive.
- Aucun gain OCR, de segmentation ou d'OLR n'est revendiqué.
