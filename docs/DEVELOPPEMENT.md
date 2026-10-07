# Développement autonome de Mille Feuilles

Le pilote de 100 pages valide un premier moteur, pas la fin du projet. Marcel a
demandé de poursuivre le développement et la discussion avec Claude. Chaque lot
doit donc produire une capacité utilisable, subir une revue croisée, être éprouvé
et déboucher sur l'attribution du suivant. La coordination reste limitée à
Mille Feuilles ; les agents et expériences Axel gardent leur propre responsabilité.

## Lot 2 : sources multiples, exclusions et partitions

Le premier démonstrateur recomposait environ 14 Ko de textes originaux. Le lot 2
apporte un import documenté, des contrôles d'exclusion dès l'entrée, une partition
par groupes et unités partagées, puis une sélection avant copie et composition.
Les segments sources sont reliés aux articles et blocs en schéma 0.3.0.

Claude possède catalogue, import, partition, leurs tests et la documentation
des actifs. Codex possède le raccordement rendu, CLI, pipeline, provenance,
validation, tests d'intégration et preuves. Chacun relit l'autre avant intégration.
L'acceptation utilise exclusivement de petits textes originaux, avec des cas
exclus volontairement. Elle exerce le CLI jusqu'au rejeu d'un lot filtré.

Les limites sont explicites : les doublons approchés ne sont pas détectés ; le
tirage par unité favorise les documents longs ; un lot filtré contient les
identités et empreintes des documents exclus de sa partition ; sans listes
externes appropriées, aucune protection des tests d'Axel n'est démontrée.
L'import ne vaut ni disponibilité d'un corpus historique ni preuve de gain réel.

## Lots suivants, dans cet ordre

1. Dégradations paramétrées et mesurées par page. Dépasser les variations légères
   `aged`/`faint`, séparer paramètres demandés et difficulté réellement observée,
   conserver une vérité géométrique correcte et éprouver les limites de lisibilité.
2. Diversité des mises en page. Ajouter des structures utiles à la segmentation
   et à l'ordre de lecture, avec une attribution et une validation explicites.
3. Éventuel profil PAGE NewsEye autonome, testé sur une fixture locale ; le lecteur
   et l'évaluation Axel restent dans leur dépôt.
4. Corpus autorisé et excluant effectivement les tests externes, puis expérience
   contrôlée sur l'utilité des données. Ne pas importer les jeux locaux d'Axel
   pour augmenter simplement le volume du démonstrateur.

Les amplitudes, interfaces et fichiers du prochain lot sont convenus avec Claude
avant écriture. Les campagnes restent compactes tant que le disque est contraint.
Aucun déplacement ni suppression des lots, corpus ou preuves existants.

Le lot 3 livré fournit un profil expérimental
`controlled-v1`, sans calibration historique : perte d'encre, contraste,
éclairage, flou et bruit. Le masque d'encre idéale est conservé avant altérations
photométriques, les générateurs aléatoires de composition et de dégradation sont
séparés, et les diagnostics sont recalculés par le validateur. Les étiquettes
`readable`, `uncertain`, `illegible` reposent sur des seuils déclarés ; elles
restent des indicateurs heuristiques, sans preuve d'équivalence à la lecture
humaine. Le verso et la simulation de numérisation plus complète sont reportés.

Son acceptation au commit `cb24e39` passe 652 tests, 224 contrôles CLI, six pages
de référence et un rejeu complet. La revue visuelle et les limites sont archivées
dans [VALIDATION](VALIDATION.md). Cette clôture porte sur le lot, pas sur le projet.

Le lot 4 en cours d'acceptation est `fr_press_19c_layout_v2` : un rez-de-chaussée à
colonnage distinct, un titre large en tête de zone principale, des corps par
article et des annonces encadrées. Il exige un profil de dégradation explicite,
dont `identity`, et conserve les chemins antérieurs. Claude possède le
planificateur, ses tests et la documentation spécifique ; Codex et ses agents
possèdent le rendu, les schémas, la validation, le CLI et les preuves d'intégration.
Les signatures sont reportées faute de texte source approprié. Les probabilités
de tirage restent déclarées et non calibrées ; aucun nouveau corpus n'est ouvert.
La revue de pages réelles a ajouté une bande équilibrée sous le titre large et
un corps normal commun aux zones. La diversité produite et les refus contrôlés
restent à mesurer par la campagne ; ils ne constituent pas une calibration.
