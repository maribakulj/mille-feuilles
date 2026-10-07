# Revue Claude du lot 3 (dégradations mesurées) — preuve autonome

Le 7 octobre 2026, Claude (Herdr w8:p2) a revu le lot 3 par contre-exemples, en lecture seule du dépôt.
Aucune commande Git en écriture n'a été lancée ; aucun corpus réel n'a été lu.

**État testé**
- Base : `7fa4b2e`, plus l'arbre de travail non commité du lot 3 (23 entrées de `git status`).
- Empreintes : `git diff | sha256` = `6fc08b8a187b8822…` ; empreinte des 12 fichiers non suivis
  = `b7cd9fcff91e6401…` (`git ls-files --others --exclude-standard | sort | xargs shasum -a 256 | shasum -a 256`).
- Les résultats ci-dessous viennent d'une **réexécution** sur cet état figé, avec la validation renforcée
  (confinement) en place.

**Répertoire** : `/private/tmp/claude-501/-Users-marcel/99660c03-830a-4e8e-be3c-f4fdedd08762/scratchpad/revue3/`
(désigné `$S` ci-dessous). Les scripts `a_c_e.py`, `jobs.py` et `forge.py` transcrivent à l'identique
les commandes directes de la première passe. `legacy.py` et `overlap.py` étaient déjà des fichiers.
Toutes les commandes se lancent depuis `~/heritage-synth`.

## Commandes
```sh
S=$S; mkdir -p $S/rerun
uv run --locked --offline python $S/a_c_e.py $S/rerun            # (a) (c) (e) + recalcul
uv run --locked --offline python $S/jobs.py $S/rerun             # (e) jobs 1 vs 2
cp -R $S/rerun/lot-j1 $S/rerun/forge
uv run --locked --offline python $S/forge.py $S/rerun/forge      # (d) faussaire cohérent
git archive 4153d99 src | tar -x -C $S/old                       # ancien code, sans mutation Git
PYTHONPATH=$S/old/src uv run --locked --offline python $S/legacy.py $S/rerun/leg-old > $S/rerun/old.txt
uv run --locked --offline python $S/legacy.py $S/rerun/leg-new > $S/rerun/new.txt   # (b) comparés ensuite
uv run --locked --offline python $S/overlap.py $S 800 1100 compacte    # ×1/×2, chevauchements, coût
uv run --locked --offline python $S/overlap.py $S 2680 3698 pilote
```

## Résultats
Pages compactes 800×1100, 4 colonnes, graine 31, index 2, sauf indication contraire.

| Point | Résultat |
|---|---|
| (a) Composition constante entre profils mesurés | **PASS** : `identity` et `controlled-v1` donnent des mots, textes, polygones, blocs et un ordre de lecture identiques |
| (b) Ancien mode sans profil comparé à `4153d99` | **PASS** : `clean`/`mixed`/`faint` × index 0 et 3, graine 77, soit 6 cas aux images PNG et pages JSON identiques octet pour octet |
| (c) Masque indépendant de la dégradation | **PASS** : masques `identity` et `controlled` identiques ; recalcul de `measure` égal au fichier ; étiquettes des pages égales aux diagnostics (1 692 readable, 4 uncertain, 7 illegible) |
| (d) Faussaire cohérent (masque « tout encre », avec diagnostics, étiquettes, exports, SHA et manifeste recalculés) | **REJETÉ** par la validation actuelle : « ideal mask has ink outside all block polygons (3 px tolerance) ». Lors de la première passe, avant l'ajout du confinement, ce même faussaire était **accepté** |
| (e) Graines et parallélisme | **PASS** : `page_seed` identique entre profils ; lot de 2 pages, `jobs` 1 et 2 : `compare` pass sur 45 fichiers |
| Ancien mode et mesuré, même graine | Compositions **différentes**, comme attendu (l'ancien mode consomme mode, papier et encre) ; documenté |

## Confinement et polygones ×2
Mesure de `overlap.py` et d'une passe directe sur `controlled-v1` (`oversampling` 1 et 2).
- **Encre du masque hors des polygones** de mots et de filets :

  | Polygones | ×1 | ×2 |
  |---|---|---|
  | stricts | 2 249 px | 391 px |
  | dilatés de 1 px | 0 | 0 |
  | hors blocs dilatés de 3 px | 0 | 0 |

- **Écart des polygones entre ×1 et ×2** : mêmes identifiants et mêmes textes ; 164 mots s'écartent de
  plus de 0,5 px, jusqu'à 3,0 px, toujours au bord droit et seulement en corps 10. La cause est l'hinting à
  20 px, plus large que deux fois l'hinting à 10 px.
- **Chevauchement entre mots voisins d'une ligne** : 0 sur 1 405 paires en compact, 0 sur 3 988 à la
  taille pilote, en ×1 comme en ×2.
- **Coût à la taille pilote** (2 680 × 3 698, `identity`, un processus) : ×1 en 9,2 s, ×2 en 12,7 s,
  pic RSS ≈ 1,07 Go.
- **Validation relue** (`_measured_page_errors`) :
  - paramètres résolus comparés exactement au profil et à la graine de dégradation ;
  - niveaux de papier, d'encre et de flou cohérents avec ces paramètres ;
  - séquence géométrique exacte ([rotation] ou [oversampling, rotation, downsample]), angle borné à ±0,35° ;
  - familles photométriques dans l'ordre FAMILIES ;
  - SHA et inventaire vérifiés avant ouverture ;
  - confinement par MaxFilter(7) ;
  - étiquettes égales au recalcul.

## Limites (à conserver dans les preuves)
- **Faussaires cohérents encore acceptés** : un masque qui remplit exactement les blocs, et un masque vide
  (tous les mots `illegible`, confinement trivialement satisfait). Le confinement ne détecte que l'encre
  hors des blocs ; il ne prouve pas la fidélité aux glyphes, que seules la reproduction et les tests du
  rendu établissent.
- **Lettres cassées** : `heuristic-v1` ne certifie pas une supervision OCR, et un mot amputé d'une lettre
  reste `readable`.
- **Rotation** : `identity` est une identité photométrique ; la rotation s'applique toujours.
- **Défaut ancien, hors lot 3** : à 800×1100 avec colonnes libres, ancien mode, 5 graines sur 40 échouent
  avec « Mot trop large pour la colonne : 'CORRESPONDANCE' » (6 colonnes).
