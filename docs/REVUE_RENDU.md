# Relecture indépendante du rendu — 7 octobre 2026

Portée : `src/mille_feuilles/render.py`, avec les actifs synthétiques embarqués.
Les tests de cette revue sont dans `tests/test_render.py`. Aucun corpus historique,
jeu de test Axel, service externe, GPU ou entraînement n’a été utilisé.

## Résultat

Après les corrections ci-dessous, **25 tests passent en 48,68 secondes** :

```sh
.venv/bin/python -m pytest tests/test_render.py -q
.venv/bin/ruff check tests/test_render.py
```

Ruff ne signale aucune erreur. Les tests couvrent :

- PNG gris 8 bits, dimensions, résolution déclarée, empreinte et marges propres ;
- couverture de chaque pixel d’encre par les enveloppes annotées sur une page
  propre, puis reconstruction pixel pour pixel depuis les textes, polygones,
  lignes de base et fontes déclarées dans les annotations ;
- inclusion mots/lignes/blocs et lignes de base, sur les trois modes de rendu,
  à la taille minimale 800 × 1100 et avec 4, 5 ou 6 colonnes ;
- reproduction identique des annotations et octets PNG après production d’une
  autre page, puis dans un autre répertoire, en modes propre, vieilli et faible ;
- provenance par document source, bornes Unicode et correspondance mot/ligne ;
- ordre contigu des articles et césure traversant deux blocs de colonnes
  différentes, avec conservation du mot reconstitué ;
- refus d’un glyphe absent, d’un caractère mappé vers `.notdef`, d’un texte non
  NFC, d’un mot non sécable trop large et des configurations invalides ;
- titre très long accepté avec toutes ses coordonnées dans l’image, ou refusé
  explicitement avant écriture du PNG.

La page propre de contrôle utilise 1200 × 1656 pixels, cinq colonnes et la graine
127. Elle exerce effectivement une césure entre colonnes ; la présence de ce cas
est exigée par le test et ne dépend pas d’un simple espoir lié au tirage aléatoire.

## Défauts trouvés et corrections vérifiées

1. **Identifiant de provenance.** Le renderer écrivait l’identifiant d’actif dans
   `source_document_id`, alors que le catalogue définit un identifiant de document
   distinct. Il utilise maintenant `metadata.source_document_id` ; le test compare
   ces valeurs et vérifie les positions dans le fichier source intact.
2. **Disponibilité du moteur typographique.** Le premier code exigeait libraqm,
   absent de l’environnement macOS utilisé. Le profil latin NFC emploie maintenant
   explicitement Pillow/FreeType `Layout.BASIC`, déclaré dans ses paramètres ; aucun
   changement de moteur implicite n’est accepté par le test.
3. **Couverture trompeuse.** Une entrée `cmap` présente pouvait pointer vers le
   glyphe manquant. Le contrôle refuse désormais aussi le glyphe d’index zéro.
   La régression modifie une copie temporaire de la fonte, jamais l’actif livré.
4. **Titres débordant l’image.** Un titre composé de 50 répétitions de « ÉDITION »,
   à 800 × 1100, quatre colonnes, graine 120, produisait 33 mots hors de l’image,
   avec une ordonnée maximale de 1164,92. Le budget utilise maintenant la hauteur
   réelle des lignes de titre, passe à la colonne suivante si nécessaire et refuse
   un titre plus haut que la colonne.
5. **Audit du style des annonces.** Les titres d’annonces et leur corps partagent
   la catégorie `annonce`, mais emploient des fontes différentes. Une reconstruction
   qui déduisait le style de la catégorie échouait sur 2656 pixels ; ce n’était pas
   une erreur géométrique. Chaque ligne déclare maintenant `extensions["mf:font"]`
   avec l’actif, la taille et le moteur. La reconstruction fondée sur ces métadonnées
   est strictement identique au PNG propre.

## Limites

Les contrôles pixel pour pixel concernent le rendu propre, avant dégradations.
Les modes dégradés sont contrôlés pour la reproductibilité, la géométrie finale et
les dimensions ; la présente suite n’établit pas à elle seule la lisibilité de
chaque mot après flou et rotation. Elle ne remplace ni la revue visuelle du pilote,
ni les contrôles des exports et de la livraison complète, ni une évaluation sur
des documents réels tenus à l’écart.

Le profil teste le français NFC avec le moteur BASIC. Il ne démontre pas le
fonctionnement d’une composition complexe, de scripts non latins ou de ligatures
OpenType discrétionnaires. Aucun gain OCR, de segmentation ou d’ordre de lecture
sur des documents réels n’est revendiqué.
