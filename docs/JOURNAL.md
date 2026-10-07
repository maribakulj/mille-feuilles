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

## Travail restant avant acceptation

1. Les contrôles de présence des planches QA et des preuves de licence sont
   terminés. La suite intégrée compte 163 tests passants avant ajout des derniers
   contrôles de rapports et outils d'acceptation.
2. Exécuter la suite finale stable et vérifier le fonctionnement depuis un
   checkout propre.
3. Produire le pilote de 100 pages sous contrôle de l'espace disque, vérifier
   toutes ses annotations/exports et inspecter les planches de contact.
4. Confirmer la reproductibilité du rendu livré et consigner les preuves,
   limites et commandes dans `docs/VALIDATION.md`.
5. Versionner et pousser le code et les preuves légères ; conserver les lots
   volumineux hors Git.

Les textes embarqués sont synthétiques et répétés. Ni leur représentativité
historique ni un gain d'OCR sur des documents réels ne sont démontrés par ces
contrôles. Les expériences comparatives avec Axel restent un chantier distinct.
