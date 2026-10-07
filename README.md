# heritage-synth (nom provisoire)

Générateur autonome de documents patrimoniaux synthétiques, destiné d'abord
à la segmentation et à l'ordre de lecture. Pilote prévu : 100 pages de presse
française du XIXe siècle, à 3–5 colonnes, avec vérité de composition et exports.

Le projet démarre par son [contrat de données](docs/CONTRAT_DONNEES.md).
Le moteur, les validateurs et les exporteurs ne sont pas encore implémentés.
Aucun entraînement ni calcul GPU n'est lancé.

- Codex : contrat, rendu, géométrie, exports, contrôles.
- Claude : cadrage historique et expérimental, corpus/fontes, adaptateur axel.
- Marcel : validation visuelle et conventions.

Axel est un consommateur indépendant. Aucun import réciproque n'est nécessaire.
Les corpus, images générées et poids de modèles n'entrent pas dans Git.
Les licences du code et des actifs restent à établir avant toute publication.
