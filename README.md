# Mille Feuilles

Répertoire local : `heritage-synth` (nom technique conservé).
Dépôt GitHub privé : [maribakulj/mille-feuilles](https://github.com/maribakulj/mille-feuilles).

Générateur autonome de documents patrimoniaux synthétiques, destiné d'abord
à la segmentation et à l'ordre de lecture. Pilote prévu : 100 pages de presse
française du XIXe siècle, avec vérité de composition et exports. Le contrat
initial prévoit 3–5 colonnes ; le cadrage propose 4–6 d'après la calibration.
Cet ajustement reste à trancher avant de figer le profil.

Le projet démarre par son [contrat de données](docs/CONTRAT_DONNEES.md).
Le moteur, les validateurs et les exporteurs ne sont pas encore implémentés.
Aucun entraînement ni calcul GPU n'est lancé.

- Coordination Mille Feuilles : session Codex dédiée, reprise le 7 octobre 2026
  à la demande de Marcel ; voir [la passation](docs/COORDINATION.md).
- Agents Claude et Codex d'Axel : transmission des travaux déjà engagés,
  puis recentrage sur Axel. Claude conserve la coordination d'Axel.
- Marcel : validation visuelle et conventions.

Axel est un consommateur indépendant. Aucun import réciproque n'est nécessaire.
Les corpus, images générées et poids de modèles n'entrent pas dans Git.
Les licences du code et des actifs restent à établir avant toute publication.

## Documents disponibles

- [Contrat de données v0.1.0](docs/CONTRAT_DONNEES.md) : format canonique,
  géométrie, transcription, exports et critères d'acceptation du pilote.
- [Cadrage historique et expérimental](docs/CADRAGE.md) : calibration de
  1 253 pages train/dev, textes, fontes, dégradations, protocole proposé,
  19 objections au contrat et 10 conventions visuelles à valider.
- [Coordination et références de reprise](docs/COORDINATION.md) : périmètre,
  responsabilités, passations et suites identifiées.
- [Passation de Codex Axel](docs/PASSATION_CODEX.md) : décisions initiales,
  état du dépôt et limites connues au transfert.

Les notes de passation et relevés de provenance conservent les chemins de
l'environnement où les travaux ont été réalisés. Les corpus correspondants
restent des ressources externes au dépôt.

## Outils et relevés reçus

[`tools/cadrage/`](tools/cadrage/) contient trois scripts Python : mesures de
mise en page (`calibrer.py`), inventaire des fontes (`fontes.py`) et vignettes
de conventions (`exemples.py`). Les distributions, la liste des fichiers lus
et l'inventaire des fontes sont versionnés dans
[`tools/cadrage/sortie/`](tools/cadrage/sortie/).

Les commandes et ressources nécessaires à leur reproduction sont décrites
au début du cadrage. Les vignettes et pages réelles restent locales ; leurs
liens dans le document correspondent à l'environnement de calibration.
