# Décisions de coordination — Mille Feuilles

Décisions du 7 octobre 2026, sous le mandat de Marcel : reprendre uniquement
Mille Feuilles, terminer la passation, créer son dépôt, puis travailler en boucle
autonome jusqu'à un système fonctionnel et éprouvé. La passation est close.
Le contrat 0.2.0 est la référence implémentable. Les demandes de validation
humaine préalable dans le cadrage historique ne suspendent pas ce mandat ; les
conventions sont décidées ici, testées et soumises à QA.

## Objections du cadrage v0.1.0

| Objection | Décision | Résolution |
|---|---|---|
| O1 — colonnes | Acceptée | Profil `fr_press_19c_columns_4_6` ; 4–6 colonnes, médiane de calibration 6. L'ancien profil 3–5 est abandonné. |
| O2 — filets dans l'ordre | Acceptée | `block_ids` contient seulement les textuels ; `unordered_block_ids` recense filets et illustrations. |
| O3 — annonces | Acceptée | Chaque annonce constitue un article propre ; ses éventuels blocs restent liés et consécutifs. |
| O4 — ordre | Acceptée | Article par article, puis blocs dans l'ordre déclaré ; les sauts de colonne restent dans le même article. |
| O5 — enveloppe/baseline | Acceptée en partie | Baseline typographique et enveloppe de composition exactes. L'inflation NewsEye est différée à un adaptateur déclaré ; elle ne modifie jamais le canonique. |
| O6 — césure interblocs | Acceptée | Deux lignes consécutives dans l'ordre du même article, y compris entre blocs/colonnes. |
| O7 — signe de césure | Acceptée | `-` visible dans le canonique ; `¬` seulement à l'initiative de l'adaptateur d'une métrique. |
| O8 — tableaux | Différée avec limite | Les tableaux simples sont définis sans fusion, ordre gauche-droite puis haut-bas. Leur production n'est pas nécessaire au premier lot ; les tableaux ambigus restent exclus, la lacune est rapportée. |
| O9 — bandeau | Acceptée | Article dédié du journal fictif ; `titre` pour le nom, `texte` pour les métadonnées composées. |
| O10 — COCO | Acceptée | Huit classes canoniques inchangées ; séparation des filets et conversion `autre→texte` relèvent d'Axel et sont documentées comme pertes éventuelles. |
| O11 — image/disque | Acceptée en partie | PNG `L` ou `RGB`, génération dimensionnable. Aucun transfert Drive automatique : une livraison locale inspectable précède tout stockage supplémentaire. |
| O12 — lisibilité | Acceptée | Dégradations bornées, état déterministe explicite, contrôle de chaque page et échantillons de mots. Aucun mot invisible n'est traité comme supervision lisible ; pas de contrôle humain mot par mot imposé. |
| O13 — document source | Acceptée | Un actif par document + `metadata.source_document_id` et même identifiant dans les spans Unicode. Source et origine synthétique sont explicites. |
| O14 — orientation | Acceptée | Somme du lacet positive dans le repère image y vers le bas ; sommets distincts, fermeture implicite. |
| O15 — calibration | Acceptée | Le manifeste empreinte protocole et `files_read: {path,sha256}` ; inventaire historique embarqué sans lecture des corpus. Partitions train/dev exclusivement. |
| O16 — symboles | Différée | Pas de substitution de fonte ni d'illustration invisible présentée comme caractère. Les symboles non couverts sont exclus avant rendu ; annotation mixte future nécessaire pour ☞. |
| O17 — transparence | Différée | Aucun verso ni transparence dans le premier profil. Une future extension devra tracer actifs/source du verso et transformation. |
| O18 — résolution | Acceptée | `provenance.parameters.render_dpi` et `image.dpi` positifs, distincts, métadonnée PNG cohérente. |
| O19 — lettrines | Exclusion acceptée | Pas de lettrine dans le pilote ; ne pas fabriquer un mot à géométrie invisible ou une lettre dupliquée entre image et ligne. |

## Conventions C1–C10

C1 : une ligne par baseline physique de titre. C2 : lettrines exclues. C3 :
filets hors articles et ordre. C4 : trait visible `-`. C5 : annonce en article
propre. C6 : ordre article par article. C7 : continuation de colonne en bloc
distinct du même article. C8 : U+0020 ; ponctuation isolée en mot. C9 : NFC
diplomatique, aucune normalisation lexicale implicite. C10 : définition des
tableaux simples fixée, génération différée sans obligation de couverture.

## Sources, expérimentation et limites

La démonstration repose sur textes originaux français documentés et fontes OFL
vérifiées. Aucun texte de test Axel, corpus tiers à droits incertains ou logiciel
BBVLM n'est copié. La calibration reçue reste traçable train/dev. Les textes
originaux permettent de prouver la chaîne de composition et la cohérence des
annotations ; ils ne prouvent pas une distribution linguistique de presse réelle.
Un corpus historique nécessitera droits documentés et filtrage des documents
protégés avant intégration. Les empreintes de n-grammes des tests, si nécessaires,
seront produites côté Axel, sans transmettre leur texte à Mille Feuilles.

Le démonstrateur n'engage aucun entraînement et ne revendique aucun gain OCR,
segmentation ou ordre sur données réelles. La comparaison R/S/R+S/S→R du cadrage
reste une expérience aval distincte. Les seuils, métriques et tests gelés d'Axel
restent sous sa coordination.

`qa/report.json` est écrit après validation et exclu du manifeste pour éviter une
empreinte circulaire. Les résultats reproductibles, la validation des exports et
les contrôles visuels doivent être consignés ; un rapport présent n'est pas à lui
seul une preuve qu'un lot modifié conserve ces résultats.
