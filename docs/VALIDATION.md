# Validation du pilote Mille Feuilles 0.2.0

## Protocole fixé avant production

Le pilote comprend 100 pages de démonstration, 2680 × 3698 pixels à 150 dpi,
graine 20261007, colonnes tirées dans 4–6, dégradations `mixed`, deux workers.
La livraison est produite depuis un commit propre avec Python 3.12 et `uv.lock`.
Les fontes et les trois documents originaux sont ceux du catalogue embarqué.
Aucune page réelle ou donnée de test d'Axel n'est lue.

L'acceptation demande toutes les preuves suivantes :

1. Suite de tests et Ruff sans erreur, actifs vérifiés ; installation depuis un
   clone neuf du dépôt, suivie d'une génération et validation par la CLI.
2. Génération des 100 pages et audit complet : JSON, géométrie, références,
   texte, césures, provenance, licences, empreintes, images et planches QA,
   XSD PAGE/ALTO et relecture des trois exports.
3. Contrôle des pixels de chaque mot sur les PNG finaux. Seuils arrêtés avant
   le calcul : contraste fond local–pixel le plus sombre ≥ 40 niveaux sur 255,
   au moins deux pixels dont l'écart au fond est ≥ 40, police effective ≥ 10 px.
   Ces seuils détectent du contenu absent ou trop faible ; ils ne prouvent pas
   une reconnaissance humaine correcte. Les minima et suspects sont rapportés.
4. Revue visuelle de chaque page sur les dix planches de contact ; examen
   supplémentaire de contours et de recadrages à résolution native couvrant
   colonnes, dégradations, césures, ponctuation et cas les moins contrastés.
5. Reproduction séquentielle des **100 images et 100 JSON canoniques**, depuis
   le même commit, les mêmes actifs et le même environnement que le pilote
   parallèle. Comparaison des octets et SHA-256, sans réécriture des métadonnées.
   Les tests de chaîne prouvent séparément la reproduction de lots complets,
   exports et planches inclus, entre un et deux workers.
6. Archivage des preuves légères dans Git, conservation des lots locaux dans
   `runs/`, puis synchronisation du dépôt GitHub privé.

L'audit de lisibilité et la reproduction sont des preuves distinctes du `pass`
de `mille-feuilles validate`. Un fichier `qa/report.json` préexistant ne dispense
pas d'un contrôle de son contenu et de l'intégrité du lot.

## Résultats

La production et les contrôles finaux sont en cours. Les résultats mesurés,
empreintes, commandes, chemins et observations visuelles seront consignés ici
après leur exécution ; ce document ne constitue pas encore une acceptation.

## Limites d'interprétation

Les textes sont originaux, synthétiques et répétés : les 100 pages ne sont pas
100 sources indépendantes. Toutes les dérivations d'un document source restent
groupées dans un éventuel découpage aval. Le pilote ne démontre pas la diversité
lexicale, la représentativité historique ou un gain de modèle sur des données
réelles. Aucun entraînement n'est lancé.

La production couvre titres, corps, annonces et filets. Tableaux, illustrations,
lettrines, verso/transparence, déformations non affines et scripts complexes sont
absents. Les dégradations sont légères et les fontes limitées à Old Standard
Regular/Bold dans ce profil. Le moteur de composition BASIC est explicite ; les
ligatures OpenType discrétionnaires ne sont pas activées.
Les césures suivent la largeur de composition, sans dictionnaire syllabique ;
les contrôles garantissent leur reconstruction, pas leur qualité linguistique.

Le fonctionnement validé est celui d'un checkout du dépôt avec l'environnement
verrouillé. La reproduction bit à bit sur un autre système ou avec une autre
version de FreeType/Pillow n'est pas revendiquée.
