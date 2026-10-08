# Journal de développement — 7 octobre 2026

## Mandat et état

Marcel a demandé la reprise de Mille Feuilles uniquement, puis la création du
dépôt privé `maribakulj/mille-feuilles`, puis une boucle autonome jusqu'à obtenir
un système fonctionnel et éprouvé. Claude et Codex Axel ont terminé leur
passation et se sont recentrés sur Axel. Aucun entraînement Axel n'est engagé ici.

L'inventaire de stockage demandé en parallèle a été écrit dans
`~/stockage/inventaire/mille-feuilles.md`. Aucun déplacement ni suppression de
données utilisateur n'a été effectué. Les lots de travail restent dans `runs/`.

## Première boucle

- Contrat 0.2.0 : profil 4–6 colonnes, gris autorisé, blocs non textuels hors
  ordre de lecture, provenance documentaire et conventions explicites.
- Actifs : quatre fontes OFL épinglées, textes de démonstration originaux,
  preuves de licence, couverture de glyphes et empreintes contrôlées.
- Moteur Pillow/FreeType BASIC explicite pour français NFC. Chaque mot est
  dessiné à la position mesurée ; lignes, mots, articles et transformations
  sont annotés. Aucun OCR utilisé pour fabriquer la vérité de composition.
- Exports PAGE 2019, ALTO 4.4 et COCO ; XSD officiels embarqués et validés
  hors réseau ; relecture du texte, ordre, catégories et géométries.
- CLI `generate`, `validate`, `compare` ; lots autonomes avec actifs,
  paramètres, environnement, provenance, contrôles visuels et empreintes.

Le premier lot à 1200 × 1656 et une page à 2680 × 3698 avec dégradations ont
passé la validation complète. Les deux rendus ont été inspectés visuellement.
Ce sont des essais de développement, pas encore le pilote final.

## Revue indépendante et corrections

Trois agents dédiés Mille Feuilles ont fourni actifs, exporteurs, validation
et revues. Les défauts suivants ont été trouvés et corrigés : identifiant
documentaire erroné, exigence RAQM incompatible avec l'environnement, couverture
de glyphe zéro, dépassement des titres longs, style des titres d'annonces
insuffisamment explicite, comparaison acceptant des lots incomplets.
La revue finale a ajouté les refus de rôles texte absents/dupliqués ou vides,
la séparation du titre et des métadonnées du bandeau, et le contrôle de tous
les champs des rapports d'export même après réempreintage.

Les tests de rendu reconstruisent une page propre pixel pour pixel depuis les
annotations et les fontes. Ils vérifient aussi les césures entre colonnes,
les transformations, les refus d'entrées invalides et la reproductibilité.
Les tests de chaîne comparent de vrais lots produits avec un et deux workers.

La première campagne de 100 pages (`runs/pilot-v0.2`) a révélé un filet de 1 px
dont deux sommets deviennent identiques après arrondi PAGE, page `mf_0029`.
Le lot non accepté est conservé. Les filets ont maintenant une épaisseur minimale
de 2 px, dans le PNG et les annotations ; la régression reproduit exactement
la page fautive, sans affaiblir le rejet des exports dégénérés. Les 26 tests de
rendu passent. Une erreur annule désormais les tâches encore en attente et
laisse finir celles déjà actives, avant de remonter l'erreur initiale.

## Acceptation du pilote corrigé

Le commit propre `0d1e2b701e9f6ba4d571a5f4894bd40071792225` passe 202 tests,
Ruff et une nouvelle installation depuis GitHub. Le pilote `runs/pilot-v0.2-r2`
contient 100 pages, 436 490 mots et 17 332 blocs ; ses 209 contrôles passent.
Un audit indépendant relit les XML de sept pages et le COCO/inventaire complet.
Les pixels des 436 490 mots passent les seuils fixés avant production.

Trois relecteurs Codex ont inspecté les 100 miniatures et 150 crops. La
reproduction séquentielle donne 100 PNG et 100 JSON identiques octet pour octet,
sans changement d'environnement. Les preuves légères et les limites sont dans
[VALIDATION.md](VALIDATION.md) et `docs/reports/`. Les lots, copies et essais
restent hors Git, sans déplacement ni suppression. La dernière livraison
documentaire conserve le commit exact de production et ne modifie pas le moteur.

Les textes embarqués sont synthétiques et répétés. Ni leur représentativité
historique ni un gain d'OCR sur des documents réels ne sont démontrés par ces
contrôles. Les expériences comparatives avec Axel restent un chantier distinct.

## Première revue réciproque Codex / Claude

Marcel a ajouté un Claude dédié au projet dans `w8:p2`. La documentation du
pilote et ses 19 preuves ont été synchronisées au commit `a135961` ; Claude
a relu ce point stable avant toute modification. Sa [note](REVUE_CLAUDE.md)
confirme l'absence de défaut dans les contrôles ciblés de rotation et de
chevauchement de lignes, et apporte trois constats traités en commun :

- C1 : limite connue des conventions PAGE lues par Axel, désormais signalée
  directement dans README, EXPORTS et VALIDATION. Aucun format modifié, aucun
  adaptateur implicite ajouté et aucune modification d'Axel.
- C2 : libellés `aged` et `faint` explicités comme variations légères, avec
  amplitudes mesurées et distinction entre seuil de contrôle et difficulté
  réellement éprouvée par les pages du pilote.
- C3 : Codex ajoute une confrontation des segments sources au texte reconstruit
  de chaque article ; Claude écrit des tests indépendants et relit le contrôle.
  L'occurrence d'un segment ne prouve pas son attribution unique lorsque le
  texte se répète, ni la couverture des textes de gabarit.

Les fichiers ont été attribués avant les écritures. Codex a relu les tests
Claude et demandé que la mutation d'une vraie page reste valide au niveau
structurel, ainsi que des cas de blocs sans article et de tableaux de stockage
réordonnés. Le test de raccordement déplace un span vers un autre passage du
même actif et recalcule l'empreinte : seul le nouveau contrôle sémantique permet
de rejeter cette provenance incorrecte.

La revue réciproque est acceptée : Claude a relu le helper et son appel après
validation structurelle, Codex a relu les 24 tests et la note corrigée.
La suite finale passe **227 tests en 143,60 s**, Ruff est sans erreur, et les
**209 contrôles** repassent sur les 100 pages conservées. Les sorties sont
archivées dans [reports/claude-review/](reports/claude-review/index.json), avec
empreintes des fichiers vérifiés. Les 19 preuves du pilote initial restent
intactes. Aucun nouveau rendu du pilote, déplacement ou nettoyage n'a été fait.

## Lot 2 — développement repris avec Claude

La clôture de la première revue au commit `654d877` a été interprétée à tort
comme une fin du développement. Marcel a demandé de poursuivre les travaux et
les échanges avec Claude. Le programme accepté commence par le corpus : import
multi-document avec exclusions avant copie, partition par groupes reliés, puis
provenance exacte des segments dans les articles et blocs (schéma 0.3.0).

Claude implémente catalogue, import et partition ; Codex intègre le rendu, le
CLI, les reçus de partition, la validation et le rejeu filtré. Les contre-exemples
de revue ont fait corriger les doublons croisés, les preuves non hachées ou mal
formées, la recherche de couverture des rôles et les limites numériques. La
validation compare aussi les comptes Unicode aux textes réellement copiés,
même si un plan et toutes ses empreintes ont été falsifiés ensemble.

La revue de Claude a identifié l'oubli de `--partition` sur un bundle partitionné.
Ce cas est désormais refusé avant création de la destination. Un lot filtré
conserve le plan et les métadonnées complètes des sources, y compris les identités
dev/test, mais aucun texte des autres partitions. Le rapport d'import suit le
lot et son rejeu ; une absence d'exclusions conserve la mention NOT EVALUATED.

Les essais utilisent uniquement de petites fixtures originales, sans lire les
corpus réels ni supprimer les productions antérieures. Les preuves finales de
ce lot sont ajoutées après exécution ; les preuves historiques 0.2.0 restent
distinctes. La prochaine attribution porte sur les dégradations mesurées.

La suite complète passe **483 tests en 176,85 s**. Elle a trouvé deux refus
de l'audit de lisibilité, encore limité à la version 0.2 ; la compatibilité
0.2/0.3 est corrigée et la version de chaque page est confrontée au manifeste.
Les seuils de pixels sont inchangés. La dernière revue Claude accepte aussi
`import_receipt`, qui relie le rapport d'import au catalogue par une bijection
exacte des documents acceptés. Ruff et le contrôle des actifs passent ; les
sorties sont conservées dans `reports/lot2/`. L'acceptation CLI suit sur commit propre.

L'acceptation CLI au commit propre `4153d99` passe : 18 documents originaux
importés et deux exclus, trois partitions à groupes disjoints, une page par
partition et les deux documents de chaque rôle réellement utilisés. Les trois
pages totalisent 4 179 mots. Le rejeu train depuis son lot filtré compare
38 fichiers identiques ; la reproduction séquentielle indépendante retrouve
exactement le PNG et le JSON. L'environnement et le code restent identiques
au début, dans chaque lot et en fin de campagne.

L'audit des 4 179 mots ne trouve aucun suspect ; trois pages, 18 crops et une
planche géométrique sont inspectés. La campagne occupe environ 20 Mo, conservés
dans `runs/accept-partitioned-v03` ; ses preuves légères sont dans
`reports/lot2/acceptance/`. Aucun corpus réel n'a été ouvert, déplacé ou supprimé.
Le lot 2 est éprouvé ; le binôme poursuit avec l'intégration du lot 3 déjà préparé
par Claude, en commençant à résolution native.

## Lot 3 — dégradations mesurées

Claude intègre profils déclarés, transformations photométriques, diagnostics et
tests indépendants. Codex raccorde la couverture idéale, le suréchantillonnage,
les diagnostics dans le lot, la validation, le CLI et la reproduction. Les fichiers
sont attribués avant écriture. Le chemin historique conserve ses PNG et JSON,
vérifiés par empreintes prises avant modification et par comparaison de Claude
contre le commit `4153d99`.

Les profils mesurés ont leur propre hasard photométrique. À paramètres de
composition identiques, identity et controlled partagent texte, coordonnées et
masque idéal ; les effets interviennent après toutes les géométries. Le facteur
×2 redessine les mêmes positions avec les fontes au double, ajuste les enveloppes
au support réel des glyphes, puis réduit la couverture grise avant seuillage.
Les diagnostics par mot utilisent le polygone exact et des seuils heuristiques
déclarés, sans prétendre certifier la lecture humaine ou l'usage comme cible OCR.

La revue des API Python directes corrige des valeurs non finies, entiers énormes,
graines invalides et familles inconnues. Le CLI refuse les deux sélections de
dégradation simultanées, même si l'ancien mode explicite vaut `mixed`.
Claude confirme le rejeu de deux pages avec workers 1 puis 2, et reproduit une
limite : un masque fabriqué avec diagnostics et empreintes recalculés ne prouve
pas les glyphes. Le contrôle d'occupation ajouté ne remplace pas le rendu de référence.
Les preuves finales du lot 3 sont distinctes de celles du lot 2 accepté.

La suite intégrée du lot 3 passe **652 tests en 349,57 s**, Ruff passe. La
revue croisée confirme le confinement et la cohérence des paramètres et des
matrices ; le faussaire tout-encre est rejeté après remise à jour complète des
empreintes, diagnostics et exports. Claude reproduit six cas historiques au
commit `4153d99` et un lot de deux pages avec workers 1 puis 2 (45 fichiers
identiques). Les preuves et ses scripts sont archivés dans `reports/lot3/`.
La campagne CLI, les coûts à taille pilote et la revue visuelle suivent.

L'acceptation au commit propre `cb24e39` passe les **224 contrôles** : six pages
de référence, 17 194 mots, trois paires identity/controlled à composition et
masque identiques, pixels distincts. Le rejeu compare 37 fichiers identiques ;
la reproduction retrouve le PNG, la page JSON, le masque et les diagnostics.
La campagne mesure 5,01–6,21 s par page compacte et 20,04–20,62 s à taille pilote,
exports et validation inclus. Le maximum RSS cumulé des processus enfants est
1 122 795 520 octets ; il n'est pas un pic attribuable à chaque profil.

Six miniatures et 17 extraits sont inspectés. Certains tirets visibles sous
identity sont étiquetés illisibles faute de pixels de masque ; des mots très
flous restent `readable` sous controlled. Les seuils restent figés et ne
certifient pas une cible OCR. La note visuelle est distincte du rapport technique
original, qui conserve honnêtement `visual_review: not_run`. Les preuves légères
sont archivées dans `reports/lot3/acceptance/`, et environ 70,25 Mo de production
sont conservés sans déplacement ni suppression.

Le lot 4 est préparé avec Claude : planificateur pur, deux zones de colonnages
distincts, titres larges, corps par article et annonces encadrées. Pendant le gel
du lot 3, le développement et les tests de ces interfaces restent dans les
scratchpads. Les essais de plan et de raccordement ne valent pas encore une
acceptation de pages rendues v2.

## Lot 4 — intégration des zones et de la bande équilibrée

Le rendu v2, le planificateur et le validateur sont intégrés. La première page
réelle révèle une perte des extensions d'article dans ALTO, corrigée avec une
régression d'aller-retour. La revue de Claude conduit ensuite à équilibrer
l'article du titre large sur toutes les colonnes couvertes, avec une bande
réservée, et à employer le corps normal de main dans le rez-de-chaussée.
Le nouveau lot compact passe ; Claude confirme les cinq lignes par colonne
et la reprise des autres articles sous la bande. Les lignes orphelines restent
une limite typographique déclarée. Les prototypes antérieurs sont conservés.

La vérification intégrée couvre **941 tests distincts réussis** : premier
passage de 931 succès, quatre échecs et quatre erreurs liés à une saturation
disque transitoire, puis reprise des huit cas et deux régressions nouvelles
(10 succès). Aucun correctif de production ni contournement des gardes disque
n'est nécessaire à cette reprise. Ruff et les actifs passent. Les commandes,
les deux sorties et la revue sont archivées dans `reports/lot4/tests-index.json`.
La campagne CLI sur commit propre et sa revue visuelle suivent séparément.

La campagne au commit propre `69f0e50` passe ensuite **284 contrôles** sur sept
pages, 20 317 mots. Le rejeu de deux pages compare 45 fichiers identiques ; la
reproduction retrouve les images, pages JSON, masques et diagnostics. Les
anciens chemins mesuré et sans profil sont prouvés séparément inchangés.
Les sept miniatures et 14 extraits sont relus par Codex, la planche et huit
extraits par Claude. La mise en page est conforme, avec limites typographiques
et heuristiques : presque tout le texte compact controlled est étiqueté illisible,
alors que des extraits restent déchiffrables à l'œil. Aucun seuil n'est retouché.
87 preuves légères sont copiées et vérifiées ; les lots complets restent locaux.
L'export NewsEye est ensuite cadré sur des fixtures originales, sans lire Axel
ni ses corpus et sans modifier les exports génériques.

## Lot 5 — projection PAGE NewsEye

Les fixtures originales et leurs attendus géométriques sont figés en `135fe97`,
puis le lecteur indépendant et ses 118 tests en `7c88927`. Claude écrit ensuite
le producteur. Les comparaisons portent sur les textes, articles, catégories,
ordre, sommets et tous les points de baseline, avec mutations contradictoires.
Les trois pages locales facultatives comprennent `mf_0003` du pilote : notre
lecteur de profil y retrouve 26 titres, 535 lignes avec article et les 14 annonces
aux rangs canoniques. Cela ne prouve pas encore une lecture par Axel lui-même.

La revue corrige un désaccord sur les chemins d'image et complète le rapport
en version 2 : 25 pertes déclarées, neuf notes. Le bundle valide la source entière
avant toute écriture, copie les octets originaux dans une destination séparée,
puis recoupe la projection avec le lecteur indépendant. Les tests découvrent
qu'un PNG peut avoir des CRC valides sans pixels décodables : le contrôle exige
aussi son décodage. Les reçus tronqués, fichiers réempreintés et changements
de source ou de code sont éprouvés sur petites fixtures. Les 249 tests dédiés
passent ; une première CLI réelle de deux pages v2 passe et écrit 6 121 724 octets.
La suite complète passe ensuite 1 190 tests en 719,42 s, avec Ruff et la
vérification des actifs réussis. Les empreintes du code sont inchangées pendant
les tests. Les sorties sont archivées dans `reports/lot5/tests-index.json` ;
l'acceptation ancrée sur commit propre suit séparément.

Au commit propre `324f60f`, la campagne NewsEye passe 376 contrôles et dix
commandes. Le pilote entier est validé avant la projection de `mf_0003` ; deux
pages v2 ×2 sont ensuite projetées et réexportées à l'identique. Les trois pages
distinctes contiennent 8 521 mots et 1 233 lignes. Les quatre refus n'écrivent
aucune destination indue ; les sources et destinations existantes sont
préservées. La campagne occupe 21 258 146 octets, sans nouveau rendu. Les 38
preuves légères sont archivées dans `reports/lot5/acceptance/`, sans les PNG,
XML ni canoniques complets. La portée reste celle du profil écrit, pas une
lecture réelle par Axel ni une preuve d'utilité pour l'apprentissage.

Le binôme poursuit A1 : rapport structurel autonome fondé sur les mesures
historiques agrégées. La revue impose les mêmes définitions, les unités
d'observation explicites, les cohortes train/dev regroupées déclarées et les
indicateurs non comparables signalés. Spécification et attendus manuels sont
figés avant le code, qui reste en scratchpad pendant l'archivage du lot 5.

## A1 — rapport structurel autonome

Les attendus manuels figés sont archivés en `2001a60`. Le module de Claude
réutilise les fonctions pures du calibrateur depuis ses octets épinglés,
sans relecture lors de l'exécution ni entrée-sortie pendant la mesure.
Les observations par page sont conservées pour réagréger les distributions
et comptes ; les catégories de comparabilité et unités sont explicites.
Le CLI exige une sélection, contrôle les annotations seules et écrit deux
fichiers dans une destination neuve.

La revue corrige `has_autre` après retrait du bandeau et un cas de D-231 où
des rectangles englobants reclassent un texte en annonce malgré des polygones
disjoints. Ces reclassements inattendus sont refusés avant mesure ; le moteur
historique reste inchangé. La note de population distingue train seul de
train/dev regroupés. Pendant une limite de session Claude, les deux dernières
corrections sont reprises par Codex, avec attribution explicite et scratch
conservé. Les attendus manuels ne changent pas.

Les 101 tests A1 et sept tests CLI NewsEye existants passent ensemble
(108 tests, 6,34 s), ainsi que Ruff. Les empreintes de code restent identiques
pendant la suite. Les sondes de 23 annotations existantes donnent 23 mesures
avec gabarit ; sans gabarit, trois mesures et 20 exclusions documentées, aucun
refus inattendu. Les preuves sont dans `reports/a1/tests-index.json`. La
campagne CLI ancrée sur commit propre suit, sans génération d'images.

Au commit `5ad97b4`, la campagne A1 passe 670 contrôles : rapports sur deux
pages v2 et deux anciennes, répétition compacte identique, quatre refus CLI,
sources surveillées intactes. Elle écrit 511 712 octets et ses 21 fichiers
sont archivés dans `reports/a1/acceptance/`. La variante sans gabarit des
anciennes pages reste ND. Ces quatre pages prouvent le fonctionnement de
la commande et non une distribution représentative ni une utilité de modèle.
Le cadrage suivant examine des articles composés d'unités consécutives d'un
même document ; aucun réglage n'est appris de cette petite campagne.

## A2 — corps à unités consécutives

Codex développe `consecutive-v1` : chaque article de corps reprend deux ou
trois unités consécutives d'un même document, titre tiré séparément, reçu
recalculable dans le manifeste. Sans l'option, sérialisation et tirages sont
inchangés. Marcel arrête Codex faute de crédits ; la
[passation](PASSATION_A2_CODEX.md) transmet un arbre non commité et deux
changements de reproduction non testés.

Claude reprend seul la coordination le 8 octobre. Le refus d'un reçu orphelin
à la reproduction est correct ; un cas du test avait une attente fausse
(rejeu sans profil rendu avec `None`), corrigée. Le script d'acceptation est
versionné dans `tools/` avec les trois corrections de revue demandées par
Codex. Suite complète : 1 423 tests passants. Commit source `e5f121a`.

L'acceptation passe 845 contrôles (voir [validation](VALIDATION.md)). La revue
visuelle ne montre pas de défaut de rendu, mais confirme une limite : des
unités consécutives du document de démonstration traitent de sujets distincts.
