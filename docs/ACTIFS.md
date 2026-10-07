# Actifs de démonstration — Mille Feuilles

Le jeu embarqué permet de composer des pages sans téléchargement à l’exécution,
sans dépendance aux corpus locaux et sans lire les tests d’Axel. Il comprend
quatre fontes OFL inchangées et trois documents français originaux, soit environ
1 Mo. Le registre est [`assets/catalog.json`](../assets/catalog.json), au format
du contrat 0.2.0 ; les chemins sont relatifs à la racine du dépôt. Le générateur
doit copier les fichiers utilisés et les preuves de droits dans le lot livré,
avec des chemins relatifs à la racine de ce lot.

## Fontes et sources

Les fichiers viennent du dépôt officiel de distribution
[`google/fonts`](https://github.com/google/fonts/tree/7085eb89a950e85db5b166b7a58d414544b4140c),
révision `7085eb89a950e85db5b166b7a58d414544b4140c`, déjà examinée lors du cadrage.
Les binaires sont conservés entiers : aucun sous-ensemble, renommage ou changement
de glyphe. Chaque famille conserve son `OFL.txt`, son `METADATA.pb` et sa
description amont ; les empreintes des preuves figurent dans le registre.

| Actif | Fichier | Version | Usage |
|---|---|---|---|
| `font_oldstandard_regular` | `assets/fonts/oldstandardtt/OldStandard-Regular.ttf` | 3.000 | Texte courant |
| `font_oldstandard_bold` | `assets/fonts/oldstandardtt/OldStandard-Bold.ttf` | 3.000 | Titres et annonces |
| `font_oldstandard_italic` | `assets/fonts/oldstandardtt/OldStandard-Italic.ttf` | 3.000 | Variantes et légendes |
| `font_gfsdidot_regular` | `assets/fonts/gfsdidot/GFSDidot-Regular.ttf` | 1.0 | Variante facultative, `ſ` |

Les licences [Old Standard](https://github.com/google/fonts/blob/7085eb89a950e85db5b166b7a58d414544b4140c/ofl/oldstandardtt/OFL.txt)
et [GFS Didot](https://github.com/google/fonts/blob/7085eb89a950e85db5b166b7a58d414544b4140c/ofl/gfsdidot/OFL.txt)
sont **SIL OFL 1.1**. Elles permettent la redistribution des fontes avec le
projet en conservant les notices ; les fontes restent sous OFL. Cette licence
n’impose pas l’OFL aux pages produites. GFS Didot porte un nom réservé ; aucune
modification n’est effectuée ici.

Limite historique : le dessin latin de GFS Didot est inspiré de Palatino,
d’après sa [description amont](https://github.com/google/fonts/blob/7085eb89a950e85db5b166b7a58d414544b4140c/ofl/gfsdidot/DESCRIPTION.en_us.html).
Son nom ne prouve donc pas une reconstitution de la typographie latine française
de Didot. Old Standard constitue le défaut de composition ; la diversité de
quatre fontes reste limitée.

## Textes originaux et format

| Actif | Source | Unités | Mots |
|---|---|---:|---:|
| `text_demo_fr` | `assets/texts/demo-fr.txt` | 30 paragraphes de corps | 2 111 |
| `text_titres_fr` | `assets/texts/titres-fr.txt` | 30 titres | 96 |
| `text_annonces_fr` | `assets/texts/annonces-fr.txt` | 12 annonces | 385 |

Les paragraphes de corps et les annonces sont séparés par une ligne vide ;
chaque titre occupe une ligne. Les fichiers utilisent UTF-8, NFC et des fins de
ligne LF, sans BOM. Ils contiennent de vrais paragraphes rédigés, et peuvent être
découpés par le compositeur en conservant les positions en points de code.
`metadata.source_document_id` identifie chaque fichier et doit être recopié
dans les `text_spans` de provenance ; `source_group_id` regroupe cette même
collection originale. Un grand nombre de pages produites ne crée pas autant de
sources textuelles indépendantes.

Ces documents ont été écrits par Codex pour ce projet le 7 octobre 2026.
Ils ne proviennent d’aucun journal, corpus OCR, Wikisource, Gallica ou document
de test. Les sujets, avis et événements sont fictifs. La
[notice locale](../assets/texts/NOTICE.md) les fournit sous **CC0 1.0** ;
le [texte officiel de CC0](https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt)
est archivé dans `assets/texts/CC0-1.0.txt`. Aucun corpus historique dont les
conditions de réemploi demanderaient un examen supplémentaire n’est embarqué.

Les textes permettent une démonstration technique autonome ; leur volume et
leur origine synthétique ne constituent pas un corpus représentatif de la
presse française du XIXe siècle. Les annonces qui mentionnent explicitement
la démonstration contribuent aussi à distinguer les rendus d’un vrai journal.
Le moteur ajoute un bandeau signalant l’édition synthétique.

## Empreintes et couverture

Le registre contient le SHA-256 de chaque actif et de ses preuves de droits.
[`assets/verify_assets.py`](../assets/verify_assets.py) vérifie les empreintes,
les chemins, la déclaration des droits, la normalisation des textes et la
couverture effective des caractères dans les tables Unicode `cmap` des fontes.
Les correspondances vers le glyphe manquant (index zéro) sont exclues.

```sh
python3 assets/verify_assets.py --report assets/coverage.json
```

Le [rapport livré](../assets/coverage.json) donne **73 caractères distincts
utilisés, aucun absent dans les quatre fontes**, dont espaces, apostrophes
typographiques, tirets cadratins, accents et `œ`. Le jeu diagnostique français
étendu, incluant les capitales accentuées et `Œ`, est également couvert.
Ce contrôle n’autorise aucun remplacement silencieux : tout nouveau texte
doit être vérifié avant son rendu avec la fonte retenue.

Old Standard n’a pas de `ſ` ; GFS Didot le couvre. Old Standard contient les
ligatures Unicode `ﬁ` et `ﬂ` ; GFS Didot contient `ﬀ`, `ﬁ`, `ﬂ`, `ﬃ`, `ﬄ`.
La couverture d’un point de code et la substitution de plusieurs caractères
par un glyphe OpenType sont deux choses différentes. Le contrôle de `cmap`
n’établit ni la justesse du shaping, ni la lisibilité visuelle : ces contrôles
restent à effectuer sur les images et annotations produites par le moteur.

Les SHA-256 exacts, versions, index de face, axes (aucun pour ces fontes fixes),
provenances et fichiers de preuve restent dans le registre, afin d’éviter une
seconde liste manuelle divergente. Aucun entraînement ni verdict de gain réel
n’est associé à cette livraison.
