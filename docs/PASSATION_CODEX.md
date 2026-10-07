# Passation Codex — 7 octobre 2026

Destinataire : nouveau coordinateur Mille Feuilles, session Codex
`01a11578-05cf-7b23-91c2-bd17c54923f3`, sur instruction de Marcel.
Cette passation concerne uniquement `/Users/marcel/heritage-synth`.

## État vérifié

- Dépôt local autonome, branche `main`, commit initial `f829bd0`
  (`Define initial heritage generator data contract`).
- Trois fichiers dans ce commit : `.gitignore`, `README.md`,
  `docs/CONTRAT_DONNEES.md` (contrat proposé 0.1.0).
- Arbre propre à la vérification précédant cette note ; cette note est un
  ajout non commité pour la passation.
- `docs/CADRAGE.md` n'existe pas encore à cette vérification.
- Aucun moteur, exporteur, schéma JSON exécutable, validateur ou jeu généré.
- Aucun calcul lourd, entraînement ou GPU lancé. Aucun fichier axel modifié
  dans le cadre du démarrage du générateur.
- Aucun processus de génération engagé par moi, aucun sous-agent lancé,
  aucune tâche générateur restant à attendre de mon côté.

## Décisions autorisées

Marcel a validé le projet autonome, le pilote de 100 pages et la priorité
segmentation/ordre de lecture. Presse française du XIXe siècle, 3–5 colonnes.
Le nom de répertoire `heritage-synth` était provisoire ; « Mille Feuilles »
était une suggestion de Claude, reprise dans le mandat du nouveau coordinateur.
Je n'ai ni renommé le dépôt ni créé de dépôt distant.

Accord initial : Codex mène contrat/rendu/géométrie/exports/QA ; Claude prend
cadrage historique, corpus/fontes, calibration, protocole et adaptateur axel ;
relecture croisée ; Marcel valide visuellement les conventions et les pages.
Deux agents suffisent au démarrage. La coordination passe maintenant au
destinataire ; je ne commence plus de tâche sur ce projet.

Le générateur n'importe pas axel. JSON canonique indépendant, projections
PAGE XML, ALTO, COCO ; adaptateur spécifique chez axel. Catégories alignées
par contrat avec `axel.layout.blocks.CATEGORIES`, consultées au commit axel
`79c5fa4050380ae80897438d365b5042e4d709ec`.

## Contrat et limites

Le contrat définit manifeste et actifs avec empreintes/provenance/droits,
graines et environnement, coordonnées de l'image finale, blocs/articles/
lignes/mots, spans Unicode, transcription diplomatique NFC, césures,
lisibilité et ordre explicite. Il interdit de confondre texte composé et
texte encore lisible après dégradation.

Calibration exclusivement sur train/dev ; test réel tenu à l'écart.
Le synthétique peut servir aux diagnostics, jamais comme seule preuve de
gain réel. Les métriques, seuils et verdicts restent chez le consommateur.
La cible E22 relève du coordinateur axel : aucune modification ici.

Version 0.1.0 proposée, pas encore relue/gelée avec Claude. Transformations
affines sans rognage de texte seulement pour le pilote. Courbures/non-affines
hors profil. Versions XSD PAGE/ALTO et projections détaillées à fixer avant
les exporteurs. Les licences du code et des actifs restent à établir avant
publication. SynthDoG/SynthTIGER est une option à vérifier, pas une dépendance
déjà installée ni un choix de moteur définitif.

Validation réalisée : lecture UTF-8, présence des huit catégories, clôture
des blocs Markdown et `git diff --cached --check`. Aucun test fonctionnel
n'est revendiqué : il n'y a pas encore d'implémentation.

## Échanges avec Claude

Claude a soutenu le projet autonome et proposé de commencer par la mise en
page. Il a proposé le pilote de 100 pages, les planches de contrôle et un
premier essai futur sur le détecteur de blocs E21. Il évoque du code de fontes
chez BBVLM ; réutilisabilité et droits n'ont pas été vérifiés par moi.

Je lui ai renvoyé deux précisions : calibration train/dev seulement ; mesures
synthétiques utiles au diagnostic, verdicts de gain exclusivement sur réel.
JEPA reste une éventuelle ablation ultérieure, pas une priorité du pilote.

Dernier message envoyé : dépôt et commit disponibles, contrat à lire,
`docs/CADRAGE.md` réservé à Claude ; signaler les objections au contrat sans
le modifier en parallèle. L'envoi a été confirmé par Herdr, mais je n'ai pas
encore reçu ni lu de réponse de fond à ce dernier message.

## Canal Claude Axel, sans interruption

Claude Axel est dans Herdr, workspace `w2`, onglet `w2:t1`, pane `w2:p1`.
Session Claude vérifiée : `a54fd04a-156e-4994-8ed0-7939d566512a`.
Titre : « Axel autonome redémarrage ». État à la passation : `working`.

Depuis un pane Herdr autorisé (`HERDR_ENV=1`), vérifier avant tout envoi :

```
herdr agent get w2:p1
herdr agent read w2:p1 --source visible
```

Pour éviter d'injecter du texte pendant son travail, attendre un état
`idle` ou `done`, puis vérifier à nouveau son identité et envoyer :

```
herdr agent prompt w2:p1 'Message de coordination Mille Feuilles…'
```

Attente bornée possible : `herdr agent wait w2:p1 --timeout 50000`.
Ne pas envoyer Escape, Ctrl-C, ni répondre à une demande d'approbation.
L'état `blocked` n'autorise pas un envoi ordinaire. Ne pas lancer un nouveau
Claude et ne pas confondre ce canal avec les autres workspaces Claude.
Un envoi confirmé ne prouve pas sa lecture ; lire sa réponse une fois terminé
avec `herdr agent read w2:p1 --source recent-unwrapped --lines 100`.

## Prochaines étapes transmises, non engagées

1. Recevoir le cadrage de Claude et relire ensemble les conventions.
2. Écrire le schéma exécutable et le validateur des invariants sémantiques.
3. Choisir le moteur après inspection du shaping, de la géométrie accessible
   et des licences ; verrouiller les profils d'export.
4. Produire une seule page et sa planche QA, puis validation visuelle.
5. Étendre aux 100 pages et satisfaire les gates du contrat avant toute
   expérience d'entraînement, sous les contraintes de calcul de Marcel.

Fin de ma contribution active au générateur à cette passation. Les travaux
et processus propres à Claude restent sous sa responsabilité, sans interruption.
