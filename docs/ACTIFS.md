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

## Import local de plusieurs documents (catalogue 0.3.0)

Le catalogue embarqué reste au format 0.2.0 ; il se charge toujours, mais ses
trois textes forment un seul groupe source : aucune partition train/dev/test
distincte ne peut en être tirée. Pour composer à partir de plusieurs documents,
on construit un **bundle** 0.3.0 avec `mille_feuilles.catalog.import_texts` :

```python
from mille_feuilles.catalog import import_texts
report = import_texts(Path("entree/import.jsonl"), Path("bundles/neuf"),
                      {"documents": Path("exclusions.txt"), "ngrams": Path("ngrams.json")})
```

Le bundle doit être absent ou vide. L'import ne télécharge rien et n'ouvre que
les fichiers nommés par le manifeste, dont les chemins sont relatifs à son dossier
et ne peuvent pas en sortir. Il copie les fontes embarquées vérifiées et leurs
preuves, mais aucun des trois textes de démonstration.

**Manifeste d'import** : JSONL, un document par ligne. Les champs obligatoires sont
`path`, `role` (`body`, `title` ou `advertisement`), `source_document_id`,
`source_group_id`, `language` (`fr`), `source_uri` et `rights` (`status`,
`license`, `evidence_path`, `attribution`, `redistribution_allowed`). Les champs
facultatifs sont `date` (ISO), `content_type` et `historical_corpus`. Tout autre
champ est refusé.

**Un actif texte = un document source**, avec plusieurs documents par rôle. Les
identifiants restent opaques : l'actif s'appelle `text_<sha256(id)[:20]>` et ses
fichiers sont rangés sous `assets/texts/imported/` et `assets/evidence/`, sous
des noms tirés de leur empreinte. Les octets sources sont conservés tels quels.

**Rejets** : chaque document refusé figure dans `assets/import-report.json` avec
ses motifs, et ses octets ne sont pas copiés. Motifs :
- droits non vérifiés ou redistribution interdite ;
- preuve absente ou vide ;
- chemin dangereux ;
- texte non UTF-8, non NFC, avec BOM, retour chariot, tabulation ou caractère
  de contrôle ;
- aucune unité de texte ;
- glyphe absent d'Old Standard Regular ou Bold ;
- document ou fichier trop volumineux ;
- identifiant de document en double, ou contenu identique à un autre : **toutes**
  les occurrences sont alors rejetées, quel que soit l'ordre des lignes. Les
  doublons sont comptés sur toutes les lignes, y compris celles rejetées pour
  un autre motif ; un doublon croisé (même identifiant avec A, même contenu avec
  C) rejette donc A, B et C.

Le bundle n'est écrit qu'après lecture et contrôle de toutes les entrées : un
dépassement du volume total arrête l'import sans rien écrire. En 0.3.0, chaque
actif doit avoir au moins une preuve locale dans `evidence_files`, avec son
SHA-256. Un `evidence_uri` local doit figurer parmi ces preuves hachées ; en
0.2.0, la notice partagée reste acceptée sous l'ancienne forme.

L'import échoue (`status: fail`, sans `catalog.json`) si l'un des trois rôles
n'a plus aucun document accepté.

**Exclusions** (protection contre les fuites vers des jeux de test externes) :
- `documents` : fichier texte UTF-8, une clé par ligne (`#` pour un commentaire).
  Une clé égale au `source_document_id`, au `source_group_id` ou au `source_uri`
  d'un document le fait rejeter.
- `ngrams` : JSON `{"format": "mille-feuilles-ngram-exclusions", "version": "1",
  "n": 8, "normalization": "nfc-casefold-word-v1", "salt_hex": …, "digest":
  "sha256-128", "hashes": […]}`. Les mots sont `\w+` après NFC et `casefold`.
  L'empreinte d'un n-gramme est `sha256(sel + 0x1F + mots joints par une espace)`,
  tronquée à 32 caractères hexadécimaux ; les empreintes sont triées et uniques.
  Un seul n-gramme protégé rejette **le document entier** : filtrer des
  paragraphes réécrirait la source et casserait la provenance. Le producteur
  externe peut utiliser `ngram_digests(texte, n, sel)`.

Un fichier d'exclusion mal formé arrête l'import avant toute écriture. Le rapport
conserve l'empreinte et le compte de chaque liste. Si l'une des deux n'est pas
fournie, il indique `external_protection: "NOT EVALUATED"` et n'affirme aucune
absence de fuite.

**Partition** : `mille_feuilles.partition.assign_partitions(bundle, ratios, graine)`
écrit `assets/partition.json`. Le graphe est recalculé à partir des fichiers du
catalogue vérifié. Deux groupes sources sont réunis dès qu'ils partagent une
unité normalisée (paragraphe ou ligne de titre, tous rôles confondus). Chaque
composante va entière dans une seule partition. L'ordre des composantes découle
de `sha256(graine:clé)`. Une recherche en profondeur, complète et bornée à
200 000 étapes, attribue d'abord à chaque partition de ratio positif des
composantes couvrant les trois rôles. Les plus grands ratios sont servis en
premier, dans l'ordre issu de la graine. Le reste est ensuite réparti de façon
gloutonne selon le nombre de caractères. Le message d'erreur distingue
l'impossibilité démontrée, quand la recherche est épuisée, du dépassement de
budget, où l'impossibilité n'est pas démontrée. Il y a au plus 32 partitions. Les ratios sont des nombres finis, positifs ou
nuls, et leur somme doit rester finie, faute de quoi ils sont refusés ; le plan
enregistre les ratios fournis. Un plan existant n'est jamais écrasé : il est renvoyé s'il est
identique, refusé sinon. `load_partition(bundle, nom)` recalcule le plan et
refuse un fichier modifié ou un catalogue changé.

Limites : la réunion par unité identique ne détecte ni les quasi-doublons ni les
reformulations. Des rubriques de titres communes (« Faits divers ») peuvent
réunir beaucoup de groupes et rendre une partition impossible ; c'est voulu, car
le système refuse plutôt que de laisser fuir. Les tests n'utilisent que des
textes originaux écrits pour eux ; aucun corpus réel n'a été importé dans ce lot.
