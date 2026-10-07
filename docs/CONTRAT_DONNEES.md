# Contrat de données — heritage-synth

Version : **0.1.0**, proposition d'implémentation du 7 octobre 2026.
Nom du projet provisoire. Ce document précède le moteur et les exporteurs ;
il ne prétend pas décrire des fonctionnalités déjà implémentées.

## 1. Périmètre et responsabilités

Le générateur autonome produit des images de pages et leur vérité de composition :
blocs, articles, lignes, mots, ordre de lecture, provenance et dégradations.
Premier profil : presse française du XIXe siècle, 3 à 5 colonnes, 100 pages.
Priorité : segmentation et ordre de lecture. Aucun modèle OCR requis.

Le JSON canonique décrit ce qui a été composé puis transformé. ALTO, PAGE XML,
COCO et le format de blocs axel sont des projections de ce JSON, jamais sa source.
Aucun import d'axel dans le générateur. L'adaptateur axel et ses évaluations
restent sous la responsabilité de Claude ; le générateur sous celle de Codex.

Le cadrage historique et expérimental sera écrit dans `docs/CADRAGE.md` par
Claude. Toute modification du présent contrat nécessite une relecture croisée.
Les conventions proposées ci-dessous pourront être amendées avant le pilote ;
un changement sémantique exige une nouvelle version et une migration explicite.

## 2. Livraison et types communs

Un lot livré possède cette structure, relativement à sa racine :

```
manifest.json
assets.json
pages/<page_id>.json
images/<page_id>.png
exports/alto/<page_id>.xml
exports/page/<page_id>.xml
exports/coco/instances.json
qa/<page_id>.png
qa/report.json
```

UTF-8 partout. JSON strict : pas de NaN, Infinity ou clé dupliquée. Tous les
chemins sont relatifs à la racine du lot, sans `..`, sans chemin absolu.
Les empreintes `sha256` sont 64 caractères hexadécimaux minuscules, calculées
sur les octets du fichier. Aucun horodatage variable dans une annotation.
Les exports et planches QA sont requis pour accepter le pilote, pas pour
valider un exemple de structure sans image.

Un `id` est une chaîne ASCII non vide conforme à `[A-Za-z_][A-Za-z0-9_.-]*`.
Un identifiant de page est unique dans le lot ; les identifiants des articles,
blocs, lignes et mots sont uniques ensemble dans une page. Les références
pointent vers le type attendu. Aucun identifiant orphelin ou réattribué.
Les nombres géométriques sont finis ; les dimensions sont des entiers positifs.
Les champs décrits sont obligatoires, sauf mention contraire. Les extensions
vont dans un objet optionnel `extensions`, avec des clés préfixées par projet.

## 3. Manifeste et actifs

`manifest.json` :

| Champ | Contenu |
|---|---|
| `schema_version` | `"0.1.0"` |
| `dataset_id` | Identifiant stable du lot |
| `profile` | `"fr_press_19c_columns_3_5"` pour le pilote |
| `generator` | `{commit, dirty, environment_path, environment_sha256}` ; commit Git complet, `dirty: false` pour livraison |
| `config` | `{path, sha256}` : configuration résolue, pas seulement les valeurs par défaut |
| `rng` | `{algorithm, version, seed}` ; seed entier entre 0 et 2^53−1 |
| `assets` | `{path, sha256}` du registre d'actifs |
| `calibration` | `{protocol_path, protocol_sha256, source_partitions}` ; partitions exclusivement `train` ou `dev` |
| `pages` | Liste de `{id, path, sha256, source_group_ids}` pointant vers les annotations |
| `artifacts` | Liste de `{path, sha256, role}` couvrant images, exports, QA et fichiers de reproduction |

`artifacts` n'inclut pas le manifeste lui-même : pas d'empreinte circulaire.
`source_group_ids` identifie les unités parentes (ex. numéro de journal) et
permet au consommateur d'éviter de séparer des dérivés d'une même source.
Le manifeste ne décide pas du split expérimental d'axel.

`assets.json` contient `{schema_version, assets: [...]}`. Chaque actif :
`{id, kind, path, sha256, source_uri, rights, metadata}`. `kind` vaut `text`,
`font`, `texture`, `illustration` ou `template`. `rights` contient
`{status, license, evidence_uri, attribution, redistribution_allowed}`.
`status` vaut `verified` ou `unresolved` ; aucun actif `unresolved` dans un lot
publiable. La preuve de domaine public des textes est documentée ; les fontes
du pilote sont OFL, licence vérifiée fichier par fichier. Aucun téléchargement
ou réemploi supposé autorisé par son seul nom.

Pour les textes, `metadata` décrit la source et les règles de préparation ;
pour les fontes : famille, version, index de face et axes variables utilisés.
L'environnement de reproduction fixe moteur de rendu, shaping, rasterisation,
dépendances et paramètres. Une graine seule ne garantit pas la reproduction.

## 4. Annotation d'une page

Objet racine :

| Champ | Type / sens |
|---|---|
| `schema_version` | `"0.1.0"` |
| `page_id` | Identifiant du manifeste |
| `profile` | Profil du manifeste |
| `image` | `{path, sha256, width, height, color_mode, dpi}` ; PNG RGB pour le pilote, dpi positif ou `null` si inconnu |
| `language` | `"fr"` pour le pilote |
| `provenance` | `{seed, template_id, asset_ids, text_spans, parameters}` |
| `transforms` | Liste ordonnée décrite en section 5 |
| `articles` | Liste de `{id, block_ids}` ; ordre logique des blocs de l'article |
| `blocks` | Liste des blocs décrits ci-dessous |
| `lines` | Liste des lignes décrites ci-dessous |
| `words` | Liste des mots décrits ci-dessous |
| `reading_order` | `{block_ids, line_ids}` : deux permutations explicites |

`provenance.text_spans` contient des `{asset_id, start, end}` : intervalles
semi-ouverts en points de code Unicode dans l'actif UTF-8 décodé, avant toute
préparation. `parameters` conserve les paramètres résolus propres à la page
(colonnes, marges, corps, interlignage, etc.). Les paramètres de shaping et
les choix de fontes font partie de la configuration résolue et des actifs.

Un bloc : `{id, category, polygon, article_id, line_ids}`.
`article_id` est `null` pour un élément hors article. Catégories fermées :
`titre`, `texte`, `legende`, `annonce`, `tableau`, `illustration`, `separateur`,
`autre`. Vocabulaire aligné sur `axel.layout.blocks.CATEGORIES`, consulté au
commit `79c5fa4050380ae80897438d365b5042e4d709ec`, sans dépendance logicielle.
`line_ids` est vide pour les blocs non textuels. Un bloc appartient à au plus
un article ; les références article/bloc doivent être réciproques.

Une ligne : `{id, block_id, polygon, baseline, text, word_ids, legibility}`.
`baseline` est une polyligne d'au moins deux points dans le sens de lecture.
Les lignes du pilote sont horizontales, de gauche à droite, éventuellement
rotées avec la page. Les tableaux à ordre ambigu sont exclus du premier profil.

Un mot : `{id, line_id, polygon, text, char_span, legibility, hyphenation}`.
`char_span: [start, end]` indexe en points de code Unicode la chaîne `text`
de la ligne ; la sous-chaîne doit être exactement le `text` du mot.
Les intervalles sont croissants et disjoints. Les caractères hors intervalles
sont uniquement des espaces U+0020. Les mots ne contiennent aucun espace.
La ponctuation attachée appartient au mot ; une ponctuation isolée constitue
un mot. Chaque mot appartient à une seule ligne, chaque ligne à un seul bloc.

`legibility` vaut `readable`, `uncertain` ou `illegible` ; c'est une décision
de génération/QA, pas une probabilité OCR. Une ligne prend l'état le plus
défavorable de ses mots. L'annotation conserve le texte composé même si une
dégradation le masque ; ce texte ne devient pas pour autant une vérité lisible.
Le pilote accepté exige des mots `readable` après contrôle visuel. Les autres
états sont réservés aux futures expériences et exclus de supervision OCR
par défaut, sans modifier silencieusement leur transcription.

## 5. Géométrie et transformations

Toutes les coordonnées d'annotation sont dans **l'image finale exportée** :
origine en haut à gauche, x vers la droite, y vers le bas, unités pixels.
On décrit les bords des pixels : domaine fermé `[0,width] × [0,height]`.
Polygone simple, au moins trois sommets distincts, aire positive, sans répéter
le premier point en dernier ; sommets dans le sens horaire à l'écran.
Les polygones décrivent les enveloppes de composition, incluant ascendants et
descendants, pas des masques d'encre ni une estimation issue d'OCR.
Mot inclus dans ligne, ligne incluse dans bloc à une tolérance de 0,5 px.
Les polygones de blocs peuvent se chevaucher si la composition l'exige.

`transforms` est une liste ordonnée de `{kind, parameters, geometry}`.
`geometry` vaut `identity` pour les dégradations photométriques ; pour une
transformation affine, c'est `{matrix: [[a,b,c],[d,e,f],[0,0,1]]}` avec
coordonnées homogènes colonne, de l'étape précédente à la suivante.
`parameters` contient toutes les valeurs résolues et la graine locale si
l'opération est stochastique. Aucun paramètre implicite dépendant d'une version.

Le pilote accepte les transformations affines sans rognage de contenu textuel.
La courbure et les déformations non affines sont hors profil 0.1 : elles
nécessiteront une carte de déplacement et une règle de densification versionnées.
Toute géométrie (polygones et baselines) subit la même transformation que
l'image. Pas de coordonnées de page propre présentées comme coordonnées finales.

## 6. Texte, césures et ordre de lecture

Transcription diplomatique, NFC ; jamais NFKC, modernisation, correction
lexicale ou suppression des accents. Conserver `ſ` et les ligatures Unicode
si elles figurent dans le texte composé. Une ligature de shaping `fi` reste
deux caractères si la chaîne était `fi` : glyphe et caractère sont distincts.
Les espaces de composition deviennent U+0020 ; pas de tabulation ni saut
de ligne à l'intérieur d'une ligne. Pas d'espace initial ou final.

`hyphenation` vaut `null`, ou `{group_id, part, reconstructed_text}` ; `part`
vaut `start` ou `end`. Dans le pilote, un groupe contient exactement deux mots
sur des lignes consécutives du même article ; le premier inclut le tiret
visible. `reconstructed_text` est une aide explicite et ne remplace jamais
la transcription de ligne. Les tirets lexicaux ordinaires ne créent pas un groupe.

`reading_order.block_ids` contient chaque bloc exactement une fois, y compris
les non textuels. `reading_order.line_ids` contient chaque ligne une fois ;
il égale la concaténation des `line_ids` des blocs dans l'ordre des blocs.
Chaque `line_ids` de bloc et `word_ids` de ligne est déjà ordonné.
La page se transcrit en joignant les textes des lignes dans cet ordre avec
`\n`, sans saut final. Pas de tri ultérieur par coordonnées ou identifiants.
L'appartenance à un article n'impose pas de regrouper les blocs à l'export.
Le profil 0.1 impose des blocs textuels contigus dans l'ordre des lignes ;
une composition qui exige leur entrelacement doit les scinder explicitement.

## 7. Projections et compatibilité

Le JSON reste conservé à côté de chaque export : aucun format ne représente
nécessairement toutes les informations. Les versions exactes des schémas XML,
leurs empreintes et les règles de projection seront fixées avant implémentation
des exporteurs ; la validation XSD sera une condition de livraison.

| Cible | Engagement |
|---|---|
| PAGE XML | Blocs, lignes, mots, polygones, baselines, texte et ordre explicite ; articles via mécanisme documenté et table des identifiants |
| ALTO | Blocs, lignes et mots, rectangles englobants, texte, ordre sérialisé et références d'articles ; conserver polygones si le profil choisi le permet |
| COCO instances | Blocs uniquement : polygons, bbox `[xmin,ymin,width,height]`, aire polygonale, `iscrowd=0` ; pas de promesse sur articles/ordre |
| axel blocks | Adaptateur chez axel : dimensions finales, `id`, `polygon`, `label=category`, `category`, `rank`, `article` si non nul, `score=1.0` comme vérité synthétique |

COCO : catégories 1 à 8 dans l'ordre de la liste de section 4 ; identifiants
numériques des pages/blocs accompagnés d'une table vers les identifiants
canoniques, sans collisions. Aire calculée sur le polygone, pas sur sa bbox.
Pour les cibles entières, arrondi documenté au plus proche, demi vers +infini,
borné au cadre ; bbox englobante arrondie vers l'extérieur. Rejeter les
polygones devenus dégénérés. Tolérance de comparaison : 1 px après export.
Toute donnée non représentable dans un format est déclarée dans le rapport
d'export et préservée dans le JSON ; aucune perte silencieuse de texte/ordre.

## 8. Contrôles et gate du pilote

Avant livraison des 100 pages :

1. JSON valides, versions compatibles, références et permutations cohérentes ;
   empreintes, dimensions d'image, chemins et provenance vérifiés.
2. Polygones simples, inclusions, baselines dans les lignes, spans Unicode et
   césures contrôlés ; aucune fonte de substitution ni glyphe absent.
3. Régénération bit à bit images/annotations dans l'environnement verrouillé ;
   rendu parallèle sans effet sur les graines ni identifiants.
4. Exports XML conformes aux XSD fixés ; relecture conservant identifiants via
   mapping, texte, ordre, catégories et géométrie selon les tolérances prévues.
5. Adaptateur axel lisant les données sans retouche manuelle ; fixture dédiée
   aux césures, ligatures, accents et articles répartis sur plusieurs blocs.
6. Planche par page : contours blocs/lignes/mots, baselines, identifiants et
   ordre ; validation visuelle des 100 pages par Marcel, anomalies consignées.
7. Registre des droits complet et `qa/report.json` avec résultat de chaque
   contrôle (`pass`, `fail`, `not_run`), détails et version de l'outil.
   Un contrôle obligatoire `not_run` empêche d'accepter le lot.

Les statistiques de mise en page et de dégradation viennent exclusivement
de train/dev. Tout gain est jugé sur un test réel tenu à l'écart. Le synthétique
sert aux contrôles et diagnostics, jamais de preuve suffisante d'un gain réel.
Les découpages, métriques, seuils et verdicts appartiennent au banc consommateur.
Aucun seuil E22 n'est modifié par ce projet.

## 9. Suite immédiate

- Claude : `docs/CADRAGE.md` (sources train/dev, droits, fontes, distributions,
  limites du profil, protocole expérimental et critères de réalisme).
- Codex : schéma JSON exécutable et validateur des invariants, puis une page
  rendue et sa planche de contrôle avant de produire le pilote complet.
- Relecture croisée du contrat et du cadrage avant de figer la version pilote.
- Choix technique SynthDoG/SynthTIGER ou autre moteur après vérification de la
  géométrie accessible et des licences ; aucun moteur imposé par le contrat.
