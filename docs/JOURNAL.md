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
