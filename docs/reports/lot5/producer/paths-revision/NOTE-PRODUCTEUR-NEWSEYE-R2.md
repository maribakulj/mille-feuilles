# Preuve RÉVISÉE (r2) du producteur `page-newseye-v1` — Claude, w8:p2

Preuve distincte de la preuve initiale (`preuve-lot5-producteur/`), qui reste **inchangée**. HEAD :
`7c88927 Verify strict independent NewsEye reader before implementing producer` ; producteur non commité, dans les trois fichiers exclusifs de
Claude.

## Correction depuis la preuve initiale
La revue de Codex a reproduit le défaut sur la fixture 1 : `project_page(image_filename=…)` acceptait
`images/a:b.png`, `images/a\tb.png`, `images/a\nb.png` et `images/a\x7fb.png`, que le lecteur
indépendant refuse.

`_image_filename` applique désormais **la même règle que le lecteur** :
- aucun deux-points ;
- aucun caractère U+0000 à U+001F ni U+007F ;
- ni `/` initial, ni `\` ;
- aucun segment vide, `.` ou `..`.

Dans les tests :
- 20 chemins refusés au lieu de 10, dont les quatre cas de Codex, `C:images/p.png`, NUL, U+001F, la barre
  oblique finale et `./` ;
- un nouveau test vérifie que trois chemins acceptés (U+0080, `é` et espace, ponctuation) le sont aussi par
  le lecteur, à l'identique.

`docs/EXPORT_NEWSEYE.md` est mis à jour. Aucun autre changement : `REPORT_VERSION` et les constantes du
rapport sont inchangés, en attente de la liste finale de Codex (pertes omises : `page.image.extensions`,
`block.extensions`, `word.extensions`, `page.reading_order.extensions`).

## Empreintes (SHA-256)
```
36dfeac4125461308824aa38d2ed81bfa24bd95ee99ce1a453f02c7c2964f249  src/mille_feuilles/exports_newseye.py
fc4bab82419b94594131faa5193a9a06f9124e22783e7a28bbf9e91726289b61  tests/test_exports_newseye.py
0dcda080530c6391660f3ce5f7b1c66f5117827fe1625fb53badb78d5f30673c  docs/EXPORT_NEWSEYE.md
4b9312c9631dfc30cfca78dc2de5c9ed81d159554ff05e8fce478e48df157be6  src/mille_feuilles/newseye_reader.py
350bb98335c33e305a073296146d3aef6eecafc1f7eb5be2c40d15cada4758ff  tests/test_newseye_reader.py
e0b8767e23e7f06bca69538f14812eacee4970db377cba683a85c2f2c8610f55  schemas/newseye-report.schema.json
```

## Sorties
- `pytest-suite.txt` : **172 passed**, soit 54 tests du producteur et 118 du lecteur.
- `pytest-pages-reelles.txt` : **3 PASSED**, pour les sondes locales facultatives, inchangées (mêmes pages
  que dans la preuve initiale).
- `ruff.txt` : All checks passed!

## Mutation (`mutate_producer.py`, dossier temporaire uniquement)
Le mutant « chemin d'image non contrôlé » de la preuve initiale ne s'applique plus au nouveau code. Il est
remplacé par **trois** mutants ciblés : deux-points accepté, caractères de contrôle acceptés, segments vides
ou `..` acceptés.
```
témoin (intact)                    54 passed in 1.93s
annonce avant son texte            1 failed, 53 passed in 1.80s
index de ligne +1                  16 failed, 38 passed in 1.14s
arrondi du banquier                5 failed, 49 passed in 1.75s
chevauchement non contrôlé         1 failed, 53 passed in 1.64s
baseline réduite aux extrémités    3 failed, 51 passed in 1.70s
article du premier bloc partout    5 failed, 49 passed in 1.70s
annonce hors de l'ordre            11 failed, 43 passed in 1.87s
bloc libre accepté                 2 failed, 52 passed in 1.73s
deux-points accepté                3 failed, 51 passed in 1.84s
contrôles U+0000..001F/U+007F acceptés 5 failed, 49 passed in 1.91s
segments vides et '..' acceptés    6 failed, 48 passed in 1.73s
apostrophe normalisée              8 failed, 46 passed in 0.97s
```
Le témoin intact passe 54 tests ; les **12 mutants sont tous détectés**.

## Limites
Celles de la preuve initiale s'appliquent toujours :
- sondes de pages réelles non versionnées ;
- mutants choisis à la main, non exhaustifs ;
- aucune revendication de gain.
