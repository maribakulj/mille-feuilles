# Coordination Mille Feuilles — reprise du 7 octobre 2026

Marcel confie la coordination de **Mille Feuilles uniquement** à la session
Codex `01a11578-05cf-7b23-91c2-bd17c54923f3` (Herdr `w8:p1` au transfert).
Axel, aussi appelé ebortz ou babaorum, reste sous sa coordination existante.
Le dépôt local Mille Feuilles reste `/Users/marcel/heritage-synth`.
À la demande complémentaire de Marcel, le dépôt GitHub privé
[`maribakulj/mille-feuilles`](https://github.com/maribakulj/mille-feuilles)
est créé et relié comme `origin`. Les livrables initiaux et ceux du cadrage
terminé sont intégrés en conservant leur historique Git.

## Passation

Les deux agents Axel ont reçu l'annonce et confirmé le transfert.
Les travaux déjà engagés sont laissés à leur terme, avec transmission des
résultats, sans interruption des processus ni des sessions. Après leur
passation, les agents Axel se recentrent sur leur projet et n'engagent pas
de nouvelle tâche Mille Feuilles.

| Interlocuteur | Livraison et état |
|---|---|
| Codex Axel, session `01a11504-8d7b-7490-8158-47b793494664` | [Passation reçue et lue](PASSATION_CODEX.md). Aucun processus ni sous-agent générateur restant de son côté. Contribution Mille Feuilles close ; recentrage Axel confirmé. |
| Claude Axel, session `a54fd04a-156e-4994-8ed0-7939d566512a`, Herdr `w2:p1` | [Cadrage reçu et lu](CADRAGE.md), scripts et relevés livrés au commit `3a943b5`. Signal de fin reçu : plus aucune tâche Mille Feuilles de son côté ; recentrage sur Axel confirmé. |

Les expériences et calculs propres à Axel restent gérés par ses agents.
Leur achèvement n'est pas une condition de cette passation Mille Feuilles.
La réception a été confirmée aux deux interlocuteurs. La passation est close.

## État reçu à la passation

- Dépôt initial : branche `main`, commit `f829bd0` ;
  [contrat de données proposé v0.1.0](CONTRAT_DONNEES.md).
- Pilote prévu : 100 pages de presse française du XIXe siècle à 3–5 colonnes,
  priorité à la segmentation et à l'ordre de lecture.
- JSON canonique indépendant ; projections PAGE, ALTO, COCO. L'adaptateur
  et les évaluations propres à Axel restent côté Axel.
- Aucun moteur, schéma exécutable, validateur, exporteur ou lot généré livré
  à la reprise. Aucun entraînement lancé pour Mille Feuilles.
- Calibration uniquement sur train/dev ; verdicts de gain sur réel tenu à
  l'écart. Les conventions, licences et versions XSD restent à finaliser.

Les attributions personnelles du contrat v0.1.0 décrivent l'accord initial ;
la présente note et le mandat de Marcel fixent la coordination actuelle.
Les responsabilités techniques et frontières entre dépôts restent applicables.

## Résultat du cadrage reçu

- 1 253 pages train/dev mesurées ; relevés dans `tools/cadrage/sortie/`,
  avec inventaire de 64 fichiers Google Fonts et d'une copie BBVLM identique
  (65 entrées, 64 empreintes distinctes). Trois scripts de
  reproduction sont livrés dans `tools/cadrage/`.
- Le cadrage propose 4–6 colonnes : médiane de 6 dans les pages AS XIXe,
  seulement 26 % dans le profil initial 3–5. Le contrat n'est pas amendé
  pendant la passation.
- Les objections O1–O19 (cadrage §7), les conventions C1–C10 (§6), les
  conditions d'usage des ressources et le protocole d'ablation restent à
  instruire. Leur réception ne vaut ni validation ni lancement d'expérience.
- Les exemples visuels se trouvent dans `~/heritage-synth-cadrage/exemples/`
  et les corpus locaux ; leurs images ne sont pas copiées dans Git.
- Claude a identifié un chevauchement E21/E7 concernant deux pages READ
  (`read_6330162-001/002`), écartées de cette calibration. Il a pris en
  charge ce constat côté Axel ; il ne relève pas d'une modification de ce dépôt.

## Ressources transmises par Claude

Références à consulter côté Axel, sans modifier ses expériences :

- Catégories de blocs : `~/axel/src/axel/layout/blocks.py`.
- Lecteur PAGE : `~/axel/src/axel/olr/page.py` ; évaluation OLR :
  `~/axel/scripts/e14_olr_eval.py`.
- Mesures lignes/pages : `~/axel/src/axel/layout/match.py` et `pagetext.py`.
- Manifestes des partitions : `~/axel/data/prepared/olr/newseye_as.json`
  et `~/axel/data/prepared/seg/manifest.json`. Leur consultation ne donne
  aucune autorisation de calibrer le générateur sur les pages de test.
- Corpus brut : `~/corpus-vt/` ; fontes candidates : `~/BBVLM/fontes/`,
  droits à vérifier avant réemploi.
- Bibliographie : `~/axel/docs/LITTERATURE.md`, sections 17–23.

## Suites transmises

1. Traiter les objections du cadrage reçu, puis réconcilier les documents.
2. Fixer le schéma, les invariants, le moteur et les profils d'export.
3. Produire une première page et sa planche de contrôle, avant les 100 pages.
4. Organiser les validations visuelles et, ultérieurement, la consommation
   des données par Axel avec son coordinateur.

Ces suites ont été engagées ensuite, sous le mandat d'autonomie de Marcel.
Le [contrat 0.2.0](CONTRAT_DONNEES.md) et les [décisions](DECISIONS.md)
résolvent les conventions et objections : profil 4–6 colonnes, actifs vérifiés,
JSON canonique, rendu et exports exécutables. Le [journal](JOURNAL.md) suit
l'implémentation et les preuves de validation. Les agents de cette réalisation
sont dédiés à Mille Feuilles ; les deux agents Axel ne sont plus sollicités.

Le pilote corrigé de 100 pages est accepté avec 202 tests passants, validation
complète des exports, revue visuelle et reproduction des 100 images/annotations.
Les [preuves de livraison](VALIDATION.md) et les limites du démonstrateur sont
versionnées. La consommation et l'évaluation sur données réelles restent côté Axel.

## Binôme Codex / Claude dédié à Mille Feuilles

Le 7 octobre 2026, Marcel ajoute un onglet Claude au projet et demande une
répartition des tâches avec revues réciproques. Il s'agit d'un nouvel agent
Mille Feuilles, distinct de Claude Axel dont la passation reste close.

| Agent | Session et contact Herdr | Première attribution |
|---|---|---|
| Codex, coordination | `01a11578-05cf-7b23-91c2-bd17c54923f3`, `w8:p1` | Synchronisation de la livraison et des preuves ; traitement des constats ; revue des contributions de Claude. |
| Claude, dédié au projet | `99660c03-830a-4e8e-be3c-f4fdedd08762`, `w8:p2` | Revue critique indépendante du code et des preuves du pilote ; recherche ciblée de défauts et retour avec sévérité, localisation et reproduction. |

Claude a reçu l'état du dépôt et confirmé la répartition. Le code source évalué est
`0d1e2b701e9f6ba4d571a5f4894bd40071792225` ; les preuves sont dans
`docs/reports/`. Cette nouvelle revue ne remplace pas les validations archivées.

Règles de travail communes :

- Annoncer le périmètre avant les modifications et attribuer des fichiers
  disjoints ; signaler les dépendances au binôme avant de toucher son périmètre.
- Faire relire une contribution par l'autre agent et traiter ses constats
  avant de l'intégrer. Codex assure initialement les opérations Git partagées.
- Laisser terminer les processus actifs ; échanger les résultats et les
  limitations, sans compter une simple prise en charge comme une validation.
- Limiter cette première revue aux contrôles ciblés : les campagnes acceptées
  sont conservées ; au début de la revue, le disque avait moins de 1 Gio libre. Ne déplacer ni
  supprimer aucun fichier, conformément à l'inventaire demandé par Marcel.
- Garder les expériences et la coordination Axel dans leur projet.

La première [revue Claude](REVUE_CLAUDE.md) est terminée. Elle a confirmé deux
contrôles géométriques ciblés, reproduit la limite du lecteur PAGE d'Axel,
demandé une formulation plus précise des dégradations et identifié un contrôle
manquant entre segments sources et texte composé. La répartition des corrections
est explicite :

- Codex : `src/mille_feuilles/validation.py`, raccordement dans
  `tests/test_validation.py`, README et documentation de contrat, exports,
  validation, journal et coordination.
- Claude : `tests/test_text_provenance.py` et `docs/REVUE_CLAUDE.md` ; revue du
  correctif et des formulations Codex.
- Codex relit les tests et la note Claude ; les conclusions de cette revue
  réciproque et les résultats d'exécution sont consignés dans le journal.

Un test spécifique au lecteur Axel n'est pas ajouté au générateur : il serait
dépendant d'un checkout externe et de conventions aval non encore adaptées.
La reproduction documentée suffit pour cette livraison ; une fixture et son
test d'intégration accompagneront l'interface de l'adaptateur à définir côté Axel.

## Reprise du développement après le premier pilote

Marcel a rappelé que la conversation avec Claude et le développement ne sont
pas terminés. La clôture de la première revue ne clôt donc pas le projet.
Le [programme de développement](DEVELOPPEMENT.md) fixe les prochains lots.

Le lot 2 passe au schéma 0.3.0 : import multi-document avec exclusions dès
l'entrée, partition des groupes reliés par unités partagées, génération filtrée,
rejeu autonome et provenance exacte des articles. Attribution exclusive :

- Claude : `catalog.py`, `partition.py`, schéma des actifs, vérification des
  actifs, tests de catalogue et partition, section correspondante d'ACTIFS.
- Codex et ses agents dédiés : rendu, pipeline, CLI, schémas page/manifeste,
  validation, tests d'intégration, reproduction, acceptation et documentation commune.

Les revues ont corrigé une attribution gloutonne déclarant à tort une partition
impossible, les doublons croisés, les preuves mal formées ou absentes, les
ratios extrêmes et la profondeur de recherche. Claude a identifié le risque
d'oublier `--partition` : un bundle muni d'un plan exige maintenant ce choix
avant toute création du lot. Les métadonnées dev/test transportées sont documentées.

L'acceptation finale est compacte et utilise des textes originaux. Claude prépare
ensuite avec Codex le lot de dégradations mesurées ; aucun corpus réel n'est
ouvert, et la fin du lot 2 ne met pas fin aux échanges ni au mandat d'autonomie.

Le lot 2 est accepté et synchronisé (`4153d99`, puis preuves `7fa4b2e`) :
483 tests, import de 18 documents originaux, deux exclusions voulues, trois
partitions et rejeu identique. Le lot 3 est effectivement engagé ensuite :

- Claude : `degrade.py`, `diagnostics.py`, schéma de profil, `profiles/`, leurs
  tests et `DEGRADATIONS.md` ; revue de l'intégration et contre-exemples.
- Codex : pipeline, CLI, reproduction, campagnes et preuves ; agents dédiés
  sur le rendu et ses tests, validation/schémas, puis intégration et acceptation.

Les interfaces sont stabilisées autour de `check_profile`, `check_parameters`
et `diagnostics.document`. Le masque d'encre idéale précède les altérations
photométriques. Chaque étape comporte une revue réciproque ; le profil mesuré
reste expérimental et n'utilise aucun corpus réel.
