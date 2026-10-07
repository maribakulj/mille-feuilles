# Mise en page v2 (`fr_press_19c_layout_v2`)

La mise en page v2 ajoute des structures utiles à la segmentation des lignes et à l'OLR :
- deux zones de colonnage distinct (zone principale et un seul rez-de-chaussée) ;
- un titre large en tête de la zone principale ;
- un corps de texte choisi par article ;
- des annonces encadrées.

Elle n'ajoute ni catégorie, ni format d'export, ni texte ou fonte nouveaux ; le seul actif nouveau est le
gabarit `template_press_v2`, qui déclare les options. Les exports PAGE, ALTO et COCO, la
provenance et la validation existants s'appliquent.

Les profils antérieurs restent identiques octet pour octet : ils n'appellent jamais le planificateur.
La v2 exige un profil de dégradation explicite (`identity` est accepté) :

```sh
uv run --locked mille-feuilles generate --output runs/essai-v2 --pages 2 \
  --width 1200 --height 1656 --dpi 67 \
  --layout-profile fr_press_19c_layout_v2 --degradation-profile identity
```

Les options sont **déclarées et non calibrées** (`calibrated: false` dans `template_press_v2`). Elles
pourront être confrontées plus tard aux relevés train/dev déjà présents dans `tools/cadrage/sortie/`, sans
nouvelle lecture de corpus.

## Options déclarées (`layout.DEFAULT_OPTIONS`, copiées dans `template_press_v2`)
| Option | Valeur | Rôle |
|---|---|---|
| `main_columns` | 4, 5 ou 6 (poids 1, 3, 6) | colonnes de la zone principale |
| `rez_de_chaussee_probability` | 0,5 | probabilité de tirage d'un rez-de-chaussée |
| `rez_de_chaussee_share` | uniforme dans [0,20 ; 0,35] | part de la hauteur de contenu |
| `rez_de_chaussee_columns` | 3, 4, 5 ou 6 (poids 1, 2, 2, 1), **toujours ≠ main** | colonnes du rez-de-chaussée |
| `headline_probability` | 0,4 | probabilité de tirage d'un titre large en tête de main |
| `headline_span` | 2 ou 3 (poids 2, 1), ramené à colonnes − 1 | colonnes couvertes |
| `small_body_ratio` | 0,82 | petit corps = max(10, arrondi(normal × 0,82)) |
| `small_body_probability` | corps 0,15, annonces 0,6 | tirage par article |
| `boxed_ad_probability` | 0,3 | annonce encadrée |
| `box_padding_px` | entier uniforme dans [3, 6] | marge entre l'encadrement et l'annonce |
| `zone_gap_px` | 8 | espace entre zones ; filet de 2 px au centre |

Ce sont des **probabilités de tirage avant contraintes**, pas des proportions observées. Les retraits par
`column_ok`, le span ramené, l'absence de titre large sous 3 colonnes, et les segments ou encadrements
que le rendu ne peut placer modifient les fréquences réelles. Les statistiques du lot rapportent ces
fréquences observées.

`layout.check_options` refuse toute option hors de ces formes :
- clé manquante ou en trop ;
- probabilité hors de [0, 1] ;
- choix vide, en double ou non entier ;
- poids nul, non fini ou de somme non finie ;
- intervalle inversé ;
- NaN, booléen ou entier démesuré.

## Tirages et traçabilité
Tous les tirages consomment le **flux de composition** de la page, dans un ordre fixe :
1. **dans le rendu** : la gouttière, puis le rapport de corps (comme le profil actuel) ;
2. **dans `layout.draw_layout`** : colonnes de main ; rez-de-chaussée oui ou non ; si oui, sa part puis
   ses colonnes ; titre large oui ou non ; si oui, son span. Les nombres de colonnes que `column_ok`
   refuse sont **retirés avant le tirage**. S'il ne reste aucune option, l'erreur est contrôlée ;
3. **dans le rendu, article par article** : le choix du segment, le petit corps et l'encadrement.

Avec `--columns c`, les options effectives remplacent `main_columns` par `{choice: [c], weights: [1]}` ;
le validateur applique la même substitution.

La dégradation garde son flux propre (lot 3) : à mise en page égale, deux profils de dégradation dégradent
la même composition.

Le plan placé est enregistré dans `provenance.parameters.layout`. Le rapport de corps tiré est enregistré
dans `provenance.parameters.layout_body_ratio`. `provenance.parameters.layout_typography` donne, zone par
zone, les tailles et interlignes des corps normal et petit. Pour le petit corps, la taille demandée,
la taille effective et le ramenage au minimum sont distingués. Le validateur peut ainsi recalculer les
corps sans ambiguïté.

## Filtre de colonnage : nécessaire, non suffisant
`column_ok(largeur)` écarte avant le tirage les colonnages où certains jetons ne peuvent pas tenir. Il
s'appuie sur un index des jetons uniques du catalogue de la page :
- **tous** les jetons des titres, qui ne sont jamais coupés ;
- pour les corps et les annonces, les jetons **non alphabétiques ou de moins de 8 caractères**, que `wrap`
  ne peut pas couper.

On compare leurs bornes d'enveloppe, union des rendus ×1 et ×2, mises en cache dans le compositeur de la
page (aucun cache global), à la largeur de colonne. Pour les annonces encadrées, on retire la marge du
cadre.

Ce filtre est **nécessaire mais pas suffisant**. Les longs jetons alphabétiques (césurables) et les
corrections d'enveloppe d'une ligne complète sont contrôlés **pendant la précomposition de chaque
candidat**. Un candidat qui ne tient pas est rejeté (voir les compteurs) ; il ne crée ni identifiant, ni
span, ni numéro de césure. `column_ok` ne garantit donc pas que chaque unité de texte tient.

Un seul jeton insécable trop large, par exemple une URL longue, exclut ce colonnage pour toute la page.
Écarter un tel jeton dès l'import reste une évolution possible, non faite en v1.

## Rejets, compteurs et erreurs contrôlées
Les compteurs sont dans `provenance.parameters` de la page :
- `layout_rejected_candidates` : candidats refusés **avant** un succès dans la zone, ou essais rejetés du
  titre large (= essais − 1) ;
- `layout_termination_rejections` : les **32** rejets consécutifs qui closent chaque zone. Ce sont des
  rejets de terminaison, pas une mesure de difficulté.

Il n'y a **pas de repli silencieux** : aucun titre large ni aucune zone n'est supprimé en cours de rendu.
Si aucun article complet ne tient sous le titre large après 32 essais, ou si aucun ne tient dans une zone,
le rendu lève une erreur contrôlée et la page échoue. Ces refus sont mesurés par des essais sur le corpus
original de démonstration.

## Positions ×1 et ×2
En v2, l'ajustement des mots utilise l'union des bornes d'enveloppe ×1 et ×2. La **composition, donc les
positions, est la même en ×1 et en ×2**. Seuls les polygones finaux diffèrent légèrement, car ils suivent
le support des glyphes du raster réellement produit.

Convention des **baselines** : `add_line` en prend les extrémités x sur l'enveloppe réelle des mots de la
ligne. Ces extrémités suivent donc le support des glyphes et peuvent différer entre ×1 et ×2, alors que la
plume est identique. Seule l'**ordonnée** de la baseline, ramenée avant rotation, est une position de
composition. Elle concorde entre facteurs à l'arrondi près (6 décimales, tolérance 1e-5 px). Les écarts
des extrémités et des polygones sont mesurés et rapportés **sans seuil** par l'acceptation ; ce ne sont
pas des invariants. Entre profils de dégradation à facteur égal, la composition entière est identique.

## Deux étapes
Le corps normal dépend de la largeur des colonnes de main, et le bandeau ainsi que le haut du contenu
(`top`) dépendent de ce corps. D'où deux étapes :
1. `draw_layout(rng, options, *, width, height, margin, gutter, column_ok, rdc_column_ok=None)` fait
   les tirages et la géométrie horizontale. Le rez-de-chaussée partage le corps de main :
   `rdc_column_ok(largeur_candidate, largeur_main)` reçoit la largeur de colonne de main tirée, telle
   qu'enregistrée dans le plan. Sans ce rappel, `column_ok(largeur_candidate)` sert aussi au
   rez-de-chaussée. Aucun rappel ne consomme le flux aléatoire ;
2. une fois `top` connu, `place_zones(draws, *, top, bottom, min_zone_height)` place les zones
   verticalement et rend un plan vérifié par `check_plan`.

Le titre large ajoute ensuite deux réservations successives :
3. `reserve_headline(plan, zone, headline_bottom, gap)` réserve le titre ;
4. `headline_columns(plan, zone)` donne les colonnes couvertes sous le titre, où l'article est équilibré ;
5. `reserve_headline_band(plan, zone, body_flow_bottom, gap, min_space_below)` réserve sa bande de corps ;
6. enfin, `columns_below(plan, zone)` donne les colonnes des articles ordinaires.

Chaque fonction de réservation rend une copie du plan, refuse un second appel et est vérifiée par
`check_plan`.

## Exemple de plan
Calculé par le planificateur (graine 4, 2 680 × 3 698, sans génération de lot). Le titre large y est réservé
avec un bas d'encre à 470 px et un espacement de 12 px. La bande de corps est réservée avec
`body_flow_bottom` = 1 105, `gap` = 14 et `min_space_below` = 24. **Les coordonnées et la part sont arrondies à
0,1 pour la lecture** : ce JSON illustre la structure. Il n'est pas le plan exact accepté par
`check_plan`, qui exige notamment la cohérence exacte entre la part et la position du filet.

```json
{"version": "1", "width": 2680, "height": 3698, "margin": 94, "gutter": 24.0,
 "zones": [
  {"id": "main", "bbox": [94, 330.0, 2586, 2750.7],
   "columns": [[94.0, 573.2], [597.2, 1076.4], [1100.4, 1579.6], [1603.6, 2082.8], [2106.8, 2586.0]],
   "headline_span": 2, "headline_reserved": [94.0, 330.0, 1076.4, 482.0],
   "headline_body_band": [94.0, 482.0, 1076.4, 1119.0]},
  {"id": "rez_de_chaussee", "bbox": [94, 2758.7, 2586, 3604.0],
   "columns": [[94.0, 908.7], [932.7, 1747.3], [1771.3, 2586.0]],
   "headline_span": null, "headline_reserved": null, "headline_body_band": null}],
 "zone_rules": [[94, 2753.7, 2586, 2755.7]],
 "rez_de_chaussee_share": 0.3, "min_zone_height": 160.0}
```

Dans cet exemple :
- `headline_columns(plan, "main")` (avant la bande) donne `[94, 482, 573.2, 2750.7]` et
  `[597.2, 482, 1076.4, 2750.7]` ;
- `columns_below(plan, "main")` (après la bande) donne `[94, 1119, 573.2, 2750.7]`,
  `[597.2, 1119, 1076.4, 2750.7]`, puis `[1100.4, 330, …]`, etc., au haut de la zone.

## Règles de composition (contrat du rendu)
- **Titre large.**
  - Il forme le premier bloc (`titre`) du premier article de la zone principale.
  - Sa bbox est l'enveloppe de son encre réelle. Le rectangle réservé (`headline_reserved`, écrit par
    `reserve_headline`) est enregistré à part.
  - Le corps de son article est **équilibré** sur les k colonnes couvertes (`headline_columns`) :
    - un bloc par colonne, dans l'ordre, chacun d'au moins 2 lignes ;
    - un écart d'au plus 1 ligne entre colonnes ;
    - le segment est utilisé entier, sans texte inventé ni répétition pour remplir ;
    - un segment trop court (moins de 2k lignes) ou trop long pour la zone est rejeté comme candidat.
  - La **bande de corps** (`headline_body_band`) va du bas de la réservation du titre à
    `body_flow_bottom + gap`, avec `gap` = 0,6 interligne (la fin d'article habituelle). Au moins une
    ligne normale (`min_space_below`) doit rester dessous.
  - `body_flow_bottom` vient de l'**enveloppe de préparation commune ×1/×2**, pour garder les mêmes
    positions entre facteurs. Les enveloppes finales de chaque facteur peuvent être légèrement plus
    petites : aucune égalité exacte avec le bas réel n'est revendiquée. Les écarts seront mesurés avant de
    fixer une tolérance de validation.
  - Les articles ordinaires reprennent **sous la bande** dans chaque colonne couverte, et au haut de la
    zone dans les autres colonnes. Ordre de lecture : le titre, ses k blocs, puis le flux colonne par
    colonne.
- **Rez-de-chaussée.**
  - C'est une zone unique, en bas de page, sous un filet pleine largeur.
  - Ses articles viennent après ceux de la zone principale dans l'ordre de lecture.
  - Il n'a pas de titre large en v1.
- **Filets de colonnes.**
  - Ils sont tracés **par zone**, dans les gouttières, sans franchir le filet de zone.
  - Entre deux colonnes couvertes par un titre large, ils commencent sous la réservation du titre et
    traversent la bande, dans la gouttière.
- **Corps.**
  - **Le corps normal est commun à toutes les zones** : celui de main, issu de la règle actuelle appliquée
    à la largeur de colonne de main. Le rez-de-chaussée garde donc le même corps avec plus de signes par
    ligne. C'est une **hypothèse de réalisme non calibrée** ; aucun rapport propre au rez-de-chaussée n'est
    introduit en v2. `layout_typography` reste enregistrée zone par zone.
  - Le petit corps ne descend jamais sous **10 px**, le minimum du profil et des heuristiques de
    lisibilité. Exemples exacts avec le rapport 0,82 :

    | Normal | Demandé (arrondi de normal × 0,82) | Effectif | Ramené au minimum | Petit corps actif |
    |---|---|---|---|---|
    | 10 | 8 (8,2) | 10 | oui | non (= normal) |
    | 11 | 9 (9,02) | 10 | oui | oui (11 → 10) |
    | 12 | 10 (9,84) | 10 | non | oui (12 → 10) |

    Le ramenage (taille demandée < 10) et l'inactivité (taille effective = normal) sont deux choses
    distinctes ; le rendu consigne la taille demandée, la taille effective et les deux indicateurs.
- **Annonce encadrée.**
  - Elle est composée à `largeur de colonne − 2 × (padding + 2)`.
  - Quatre filets de 2 px l'entourent à `padding` px. Ces filets restent hors article et hors ordre de
    lecture.

## Invariants vérifiés par `check_plan`
- Racine en objet, clés exactes du plan et des zones, version `"1"`.
- Largeur, hauteur et marge sont des entiers bornés (100..20 000 px) ; gouttière ≥ 0 ;
  `min_zone_height` > 0 ; tous les nombres sont finis.
- Les zones sont `main`, puis éventuellement `rez_de_chaussee`.
- Bboxes dans les marges de page, horizontalement et verticalement ; aucune zone plus basse que
  `min_zone_height` ; pas de chevauchement.
- Au moins deux colonnes par zone, triées, séparées au moins par la gouttière et contenues dans leur zone.
  Le rez-de-chaussée a un nombre de colonnes différent de celui de main.
- `headline_span` est dans 2..colonnes − 1, et seulement dans main. Une réservation n'existe qu'avec un
  titre large, alignée sur ses colonnes et au haut de la zone.
- Une bande de corps n'existe qu'avec une réservation de titre. Elle est alignée sur les mêmes bords
  horizontaux, commence exactement au bas de la réservation et finit avant le bas de la zone. L'espace
  minimal sous la bande est contrôlé par `reserve_headline_band`, puis par la validation des pages (qui
  connaît la typographie) ; il n'est pas stocké dans le plan.
- Un filet de zone par frontière, exactement de la largeur de la zone, d'au moins 2 px de haut et compris
  entre les deux zones.
- `rez_de_chaussee_share` est présent si et seulement si le rez-de-chaussée existe, et cohérent avec la
  position du filet.

Les autres invariants (non-chevauchement des blocs, un bloc d'au moins 2 lignes par colonne couverte avec
un écart d'au plus 1 ligne, blocs de l'article contenus dans la bande, articles ordinaires sous la bande, ordre
par zones, encadrements fermés, filets sans intersection avec le texte dans ce profil) relèvent de la
validation des pages.

## Limites
- Les options sont déclarées, pas calibrées. Aucun gain de segmentation ou d'OLR n'est revendiqué.
- Absents de v1 :
  - signatures (aucun rôle de texte existant ne les source ; pas de texte inventé ni de paragraphe
    détourné) ;
  - tableaux, illustrations et lettrines ;
  - suites d'article sur une autre page ;
  - colonnes inégales dans une zone ;
  - plus d'un rez-de-chaussée ;
  - titre large ailleurs qu'en tête de main.
- La vérification du plan ne garantit pas que le texte rendu respecte le plan : c'est le rôle de la
  validation des pages et des tests du rendu.
