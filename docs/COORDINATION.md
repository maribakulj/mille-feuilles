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
