# Rapport structurel A1 : pages Mille Feuilles et relevés agrégés du cadrage

`mille_feuilles.realism` compare la **structure** de pages canoniques Mille Feuilles aux statistiques agrégées
du cadrage (`tools/cadrage/sortie/calibration.json`). C'est un **contrôle descriptif** : il ne donne aucun
verdict de gain, ni pour l'OCR ni pour la segmentation, et ne note pas un « réalisme global ».
L'intervalle p10–p90 réel est une description, pas un seuil d'acceptation ni un intervalle de confiance.

Spécification : [SPEC-A1 révision 2](reports/a1/spec/SPEC-A1.md),
[amendement r2.1](reports/a1/spec/AMENDEMENT-r2.1.md) et
[décisions de revue](reports/a1/spec/REVIEW-AMENDMENTS.md).

## Commande et portée du rapport

```sh
uv run --locked mille-feuilles report-structure --from runs/mise-en-page-v2 \
  --output runs/structure-v2 --page mf_0000 --page mf_0001 --reference as:XIXe
```

La sélection est explicite : `--page` est répétable, ou `--all-pages` sélectionne toutes les pages du
manifeste. La destination doit être neuve et séparée du lot ; elle contient exactement `report.json`
et `report.sha256`. Le rapport conserve les mesures par page, les agrégats et les empreintes des entrées.
Son recalcul demande les fichiers canoniques sélectionnés correspondant à ces empreintes.

La commande vérifie le manifeste, les empreintes et la structure des JSON sélectionnés. Elle ne valide
pas le lot complet : images, actifs, exports, droits et provenance textuelle ne sont pas revérifiés.
Elle ne rouvre aucun corpus réel et ne réévalue pas les exclusions du cadrage. Les limites sont de
100 pages, 200 Mo de JSON canoniques et 20 Mo de sortie, avec une réserve disque de 500 Mo. Un calcul
réussi atteste l'exécution de ce diagnostic, sans verdict sur le réalisme ou les gains OCR.

## Mêmes définitions, sans corpus
Les mesures sont **celles de `tools/cadrage/calibrer.py`**, exécutées depuis ses octets exacts.
`load_engine` :
1. lit le fichier **une seule fois** ;
2. vérifie son SHA-256 (`CALIBRER_SHA256`), sinon refus `sha_calibrer` avant toute compilation ;
3. compile ces octets dans un module neuf (`mille_feuilles._calibrer_cadrage`, différent de `__main__`),
   sans relecture, sans `.pyc` et sans inscription dans `sys.modules`.

Seules les fonctions pures sont appelées : `mesurer`, `q` et leurs aides. `main`, `Journal`, `image_dpi*` et
`_head` ne le sont jamais, et aucun fichier de corpus n'est ouvert. `calibration.json` est lu après
vérification de son SHA-256. Pendant `measure_pages` et `aggregate`, **aucune entrée-sortie** n'a lieu ; un
test le prouve en piégeant `open` et les lectures de `Path`.

L'adaptateur `canonical_to_pg` construit, pour chaque page canonique, la structure qu'aurait produite
`calibrer.parse_page` :
- blocs textuels → TextRegion (`heading` pour titre, `caption` pour légende), avec leurs lignes (polygone,
  baseline, texte et article du bloc) ;
- annonce → TextRegion **et** AdvertRegion de même polygone ;
- filet → SeparatorRegion ;
- illustration → GraphicRegion ;
- ordre = `reading_order.block_ids`.

La géométrie est **native** : pas de nouvelle rotation, pas d'arrondi d'export. `dpi` vaut toujours `None`
en v1 : les unités physiques ne sont pas mesurées, et le DPI déclaré n'est rapporté qu'en métadonnée.

Avant chaque mesure, les catégories et identifiants des blocs conservés sont confrontés au résultat
de `type_blocks`. Tout changement de catégorie ou disparition est refusé (`category_retyping`), avec
la page, les identifiants et les catégories avant/après ; seul `autre` → `texte`, déjà déclaré dans la
matrice, est admis. Ce contrôle est nécessaire car D-231 calcule certains recouvrements avec des
rectangles englobants : des polygones pourtant disjoints peuvent provoquer une réinterprétation.
Le moteur historique reste inchangé ; A1 refuse alors la page plutôt que d'en présenter une mesure
comme équivalente. Le contrôle porte sur les blocs retenus dans chaque variante de gabarit.

## Comparabilité de chaque indicateur
| Statut | Signification |
|---|---|
| C | même code, entrée équivalente |
| A | même code, mais une différence d'entrée connue. Exemples : le bandeau MF compté comme article de gabarit ; les catégories canoniques retypées par la règle D-231 |
| NC | calculable mais non comparable en sémantique. `annonce_avec_titre` : l'en-tête d'annonce MF est catégorisé `annonce`, donc un 0 est structurel |
| ND | absent d'un côté (l'absence ne vaut pas zéro), unités physiques avec `dpi=None`, PrintSpace, chemins KB/BnF |

Ces quatre statuts sont les seuls statuts publics. Chaque entrée de `compare` donne aussi :
- `definition_status`, le statut de la matrice, conservé même si `status` devient ND faute d'observation ;
- `comparison_allowed` et sa raison. Les mesures en pixels sont A avec `comparison_allowed: false` : elles
  sont rapportées mais non comparées, car les résolutions diffèrent ;
- `sample_unit`, l'unité d'échantillonnage : page, colonne, gouttière, article, annonce, titre rattaché à
  un article, ligne de titre, filet vertical, ou compte par catégorie ;
- `kind` : `distribution` (quantiles de `q`) ou `counts` (valeur et part, traités séparément).

Règles dynamiques :
- un indicateur absent d'un côté devient ND ;
- avec n = 1 (sans p10 ni p90), il est non comparé ;
- les comptes par catégorie (`blocs_nombre`, `blocs_surface`, `ordre_transitions`) sont rapportés en
  `valeur` et `part`, sans quantiles ;
- si une page contient un bloc `autre`, lu `texte` par D-231, les métriques de texte passent en A ;
- `ordre_transitions` reste C : il classe les déplacements géométriques entre blocs successifs, sans
  distinguer `autre` et `texte`. Sa classe spatiale `autre` n'est pas une catégorie de bloc ;
- un bloc `tableau` est refusé (`table_block`).

Définitions à connaître :
- surfaces = aires polygonales ;
- ordonnée de baseline = moyenne de **tous** ses points ;
- largeur de colonne = statistique d'ordre `widths[floor(0,75 × (n − 1))]`, différente d'un quantile ;
- colonnes **inférées** par l'heuristique historique, et non colonnage déclaré ;
- médianes de page puis quantiles entre pages, et non ensemble des lignes poolées.

## Cohortes
- **Réel** : `as:XIXe` par défaut. Ses 65 pages sont **train et dev regroupés** (53 + 12), parce que
  `calibration.json` ne les sépare pas. Seul l'histogramme des colonnes est donné par split. Aucune
  sous-cohorte (train seul, 4–6 colonnes) n'est possible sans recalibration.
  La note de population suit les splits effectivement présents : `bnf:XIXe`, `read` et `kb`, par
  exemple, ne contiennent que train et ne sont donc pas décrits comme un regroupement train/dev.
- **Mille Feuilles** : la liste explicite de pages canoniques fournie. Pour chaque page, le rapport donne
  profil, angle, oversampling, DPI déclaré et colonnage déclaré.
- **Variantes** :
  - `avec_gabarit` (protocole historique, comparaison principale) ;
  - `sans_gabarit`, une **analyse de sensibilité** au bandeau. Une page sans `mf:template_article_ids`
    (page 0.2.0, par exemple) est exclue de cette variante, sans retrait fictif. Si **au moins une** page
    de la cohorte est exclue, la variante est **ND au niveau de la cohorte** : les observations partielles
    restent rapportées avec les identifiants des pages et les exclusions, mais aucune comparaison n'est
    présentée, car elle ne porterait pas sur les mêmes pages que la variante principale.

Mesure page par page : `measure_pages([page], engine)` puis `merge_measures(parts)` (valeurs concaténées,
comptes sommés) donnent exactement le résultat d'un appel groupé. `aggregate(measures, engine)` puis
`compare(stats, reference["stats"], has_autre=…)` s'appliquent ensuite sans garder les canoniques en
mémoire. Ces signatures sont stables pour l'orchestrateur ; `build_report` n'est qu'une aide exploratoire.

## Exemple (essai du 7 octobre 2026, 23 pages, variante avec gabarit)
Pages : 2 pages compact-identity ×1 et 1 page pilote controlled ×2 de l'acceptation du lot 4, et 20 pages du
pilote r2. Réel : `as:XIXe`.

| Indicateur | Statut | MF p50 | Réel p10 / p50 / p90 | Position |
|---|---|---:|---|---|
| signes par ligne | C | 46 | 39 / 42 / 48 | p10–p90 |
| colonne / interligne | C | 18,2 | 19,2 / 22,5 / 27,1 | < p10 |
| part de lignes en césure | C | 0,109 | 0,137 / 0,210 / 0,237 | < p10 |
| colonnes inférées | C | 6 | 5 / 6 / 6 | p10–p90 |
| interligne / H | C | 0,0062 | 0,0042 / 0,0048 / 0,0055 | > p90 |
| articles par page | A | 74 | 18 / 33 / 57 | > p90 |
| `annonce_avec_titre` | NC | 0 | 0 / 0 / 1 | non comparé |
| hauteur de ligne en px | A (comparaison interdite) | 21 | 37 / 50 / 60 | non comparé |

**Lecture prudente** :
- ce sont des positions descriptives d'un petit échantillon de pages de démonstration, pas des cibles ;
- dans cet essai, la variante sans gabarit est ND au niveau de la cohorte : les 20 pages du pilote r2
  (format 0.2.0) n'identifient pas leur bandeau ;
- aucune modification du générateur (A2) n'est engagée sur la base de ce rapport sans revue.
