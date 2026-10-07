# Exports Mille Feuilles — profil 0.2.0

Le JSON canonique reste la source de vérité. Les fichiers XML et COCO sont
des projections déterministes, accompagnées d'un rapport par page. Ils
n'attestent ni un gain OCR ni une validation historique du rendu.

## Schémas officiels et validation hors réseau

| Format | Version figée | Source primaire |
|---|---|---|
| PAGE | 2019-07-15 | [XSD PRImA](https://www.primaresearch.org/schema/PAGE/gts/pagecontent/2019-07-15/pagecontent.xsd) |
| ALTO | 4.4 | [XSD Library of Congress](https://www.loc.gov/standards/alto/v4/alto-4-4.xsd) |
| XLink, dépendance ALTO | METS XLink Schema v2, 15 novembre 2004 | [XSD Library of Congress](http://www.loc.gov/standards/xlink/xlink.xsd) |

ALTO 4.4 est la version officielle indiquée par la
[Library of Congress](https://www.loc.gov/standards/alto/). Elle permet les
groupes d'ordre explicites, les polygones des blocs/lignes/mots, et les
baselines composées de plusieurs points. Le dépôt officiel
[PAGE-XML](https://github.com/PRImA-Research-Lab/PAGE-XML) identifie le XSD
2019 ; sa branche principale peut décrire une version ultérieure, elle
n'est donc pas utilisée comme schéma de validation.

Les fichiers sous `schemas/xml/` sont archivés **sans modification**.
`schemas/xml/provenance.json` fixe leurs URL, versions, SHA-256 et
dépendances. La licence Apache-2.0 de PAGE est conservée dans
`PAGE-LICENSE`. La licence CC BY-SA 4.0 d'ALTO est inscrite dans son en-tête.
XLink conserve son en-tête d'origine ; aucune licence supplémentaire
n'est supposée. L'URL XLink HTTP officielle fonctionnait lors de l'archive,
alors que sa variante HTTPS renvoyait 404.

Le résolveur lxml redirige seulement l'import XLink connu vers la copie
locale. Il refuse les autres URL externes ; le parseur désactive réseau
et expansion d'entités, et le validateur refuse les `DOCTYPE`. Aucun XSD
allégé ou construit spécialement pour accepter les exports n'est utilisé.

## API et fichiers requis

```python
from pathlib import Path
from mille_feuilles.exports import export_page, export_coco, validate_exports

root = Path("lot")
paths = export_page(page, root)  # dict page / alto / report, relatifs au lot
coco_path = export_coco(pages, root)  # Path vers instances.json
errors = validate_exports(root, pages)  # [] signifie tous contrôles réussis
```

Fichiers requis : `exports/page/<id>.xml`, `exports/alto/<id>.xml`,
`exports/reports/<id>.json`, `exports/coco/instances.json`.
Les chemins d'images inscrits dans les exports se résolvent depuis la
racine du lot, conformément au contrat. Le lecteur doit donc utiliser la
racine du lot comme base, y compris quand le XML est dans un sous-dossier.

### Lecture par Axel : adaptateur encore nécessaire

La revue Claude du 7 octobre 2026 a chargé l'export PAGE `mf_0003` du pilote
avec le lecteur local `axel.olr.page.load_page`, spécialisé dans les conventions
NewsEye. Il lit 89 blocs textuels, mais reconnaît **0 des 26 titres**, aucun
article sur les **535 lignes**, et reporte les **14 annonces** en fin d'ordre.
Ce lecteur attend des structures dans `custom`, alors que notre profil utilise
le type PAGE natif et du JSON complémentaire ; il ordonne les `TextRegion`
enfants des annonces indépendamment de leur conteneur référencé.

Il faut donc un adaptateur explicite avant d'utiliser ces exports dans les
métriques Axel. Aucun adaptateur ni changement d'Axel n'est livré ici. Ce
constat ne remet pas en cause la conformité XSD et ne constitue pas un essai
d'autres lecteurs. La [revue](REVUE_CLAUDE.md) conserve la reproduction ; un
test d'intégration devra accompagner l'interface de l'adaptateur une fois fixée.

Le validateur vérifie les empreintes de l'archive XSD, la conformité XML,
puis relit les **valeurs effectivement exportées** : identifiants,
transcriptions des mots et lignes, ordre des blocs et lignes, catégories,
articles, géométries, baselines, spans, lisibilité et césures. Pour COCO,
il vérifie dimensions, catégories, identifiants, mappings, références,
segmentations, bbox, aire et `iscrowd`. Une absence, incohérence ou
différence devient une erreur, jamais un contrôle implicitement réussi.
Le contrôle canonical JSON complet et les empreintes du lot appartiennent
à `validate_dataset` ; `validate_exports` couvre la projection.

## Identifiants, ordre et géométrie

Les IDs XML sont `b_<id>` (bloc), `l_<id>` (ligne), `w_<id>` (mot).
Les autres préfixes sont réservés : `a_` article, `h_` césure, `s_` espaces,
`p_` page, `r_` référence ALTO, `c_` conteneur textuel PAGE et `mf_` groupes
d'ordre. Le rapport donne le mapping complet XML → canonique et le mapping
des conteneurs. Il distingue les huit catégories du contrat sans les
fusionner.

L'ordre sérialisé est `reading_order.block_ids` suivi de
`unordered_block_ids`. Les lignes et mots suivent uniquement `line_ids`
et `word_ids` ; les tableaux de stockage et les coordonnées ne définissent
jamais l'ordre. Les éléments graphiques restent hors de l'ordre textuel.
Un article peut traverser des blocs/colonnes ; son appartenance et son
ordre interne ne sont pas reconstruits depuis la position de ses blocs.

PAGE exige des coordonnées entières : `floor(x + 0.5)`, borné au cadre,
pour chaque coordonnée finale. Un polygone qui perd un sommet, son aire
positive ou sa simplicité à l'arrondi est refusé. Une baseline réduite
à un point est également refusée. La relecture exige l'arrondi documenté,
soit au plus 0,5 px d'écart par coordonnée et moins de 1 px euclidien.
ALTO et COCO conservent les coordonnées décimales ; leurs bbox sont les
rectangles englobants exacts. L'aire COCO est celle du polygone par la
formule du lacet, pas celle de la bbox. Aucun polygone n'est élargi pour
ressembler aux annotations NewsEye ; cette adaptation reste séparée.

## PAGE 2019

`titre`, `texte`, `legende`, `autre` deviennent des `TextRegion`, de type
`heading`, `paragraph`, `caption`, `other`. `illustration` devient
`GraphicRegion`, `separateur` devient `SeparatorRegion`.
`annonce` et `tableau` deviennent `AdvertRegion` et `TableRegion` ; si le
bloc contient du texte, un `TextRegion` enfant `c_<id>` porte ses lignes,
car ces types de région ne permettent pas des `TextLine` directs. Ce
conteneur reprend la géométrie du bloc et ne crée aucun bloc canonique.
Le schéma autorise cette imbrication.

L'attribut standard libre `custom` contient un objet **JSON** UTF-8 :

| Élément | Champs conservés |
|---|---|
| Région de bloc | `category`, `article_id` (`null` si absent) |
| Ligne | `legibility` |
| Mot | `char_span`, `legibility`, `hyphenation` |

Les articles, avec leurs listes ordonnées de blocs, sont un JSON dans
`Metadata/UserDefined/UserAttribute[name='mille-feuilles:articles']`.
Ce JSON est une convention Mille Feuilles, pas la grammaire `custom`
d'un autre producteur. Un consommateur doit la lire explicitement.
L'export natif n'est pas présenté comme l'adaptateur NewsEye/Axel.

Chaque ligne a un `index` local et son `TextEquiv/Unicode` exact. Les mots
portent également leur transcription exacte. Le texte de région est la
jonction des lignes avec `\n`. L'ordre des blocs textuels figure dans un
`OrderedGroup` placé sous un `UnorderedGroup` racine ; les autres régions
sont des `RegionRef` non ordonnés de cette racine.

Les deux dates obligatoires PAGE valent `1970-01-01T00:00:00Z`, sentinelle
de reproduction signalée dans `Comments`, et ne prétendent dater ni le
document source ni son export réel.

## ALTO 4.4

Les blocs textuels sont des `TextBlock`, les illustrations des
`Illustration`, les filets des `GraphicalElement`. Catégories exactes,
articles et lisibilité sont portés par les mécanismes standards
`Tags`/`TAGREFS` :

| Type de tag | `TYPE` | Données |
|---|---|---|
| `LayoutTag` | `mille-feuilles:category` | `LABEL` = catégorie canonique |
| `StructureTag` | `mille-feuilles:article` | `LABEL` = article ; `DESCRIPTION` = JSON `{block_ids}`, complété par `extensions` si l'article en possède |
| `OtherTag` | `mille-feuilles:legibility` | `LABEL` = état canonique |
| `OtherTag` | `mille-feuilles:hyphenation` | `LABEL` = groupe ; `DESCRIPTION` = texte reconstruit |
| `OtherTag` | `mille-feuilles:spaces` | `LABEL` = ligne ; `DESCRIPTION` = JSON des nombres d'espaces entre mots |

Les tags d'espacement ne sont émis que si un intervalle diffère d'un
espace. Un `SP` représente la présence d'un espace, sans promettre sa
géométrie ; sa multiplicité textuelle vient du tag. Ignorer ce tag perd
les espaces multiples. Les `char_span` Unicode sont reconstruits depuis
les `String/CONTENT` et ces intervalles ; ils sont vérifiés à la relecture.
Les lignes vides sont refusées : ALTO impose au moins un `String` dans
une `TextLine` dans ce profil.

Les extensions d'article, notamment les réservations de mise en page v2,
restent dans ce JSON du `StructureTag` et sont confrontées au canonique à la
relecture. PAGE les transporte déjà avec l'objet article complet. Un lecteur
qui ignore ces métadonnées spécifiques ne récupère pas leur sémantique ; les
polygones, références d'article et ordre restent les projections documentées.

Une césure garde son texte diplomatique, tiret compris, dans `CONTENT` ;
`SUBS_TYPE=HypPart1/HypPart2` et `SUBS_CONTENT` portent la reconstruction.
Le groupe canonique vient du tag de césure, y compris entre deux blocs.
Le tiret n'est pas dupliqué dans un `HYP`. Les tirets lexicaux n'ont pas
de substitution. Ni `WC` ni `CC` ne sont inventés : la lisibilité n'est
pas une confiance OCR.

Le `ReadingOrder` ALTO porte un `OrderedGroup` pour les blocs textuels
et, si nécessaire, un `UnorderedGroup` pour les autres. Chaque niveau
bloc/ligne/mot conserve `Shape/Polygon` et sa bbox ; les lignes conservent
la polyligne `BASELINE` finale.

## COCO et pertes explicites

COCO ne porte que les blocs. Les classes 1–8 sont, dans cet ordre,
`titre`, `texte`, `legende`, `annonce`, `tableau`, `illustration`,
`separateur`, `autre`. `segmentation` contient un polygone, `bbox` vaut
`[xmin,ymin,width,height]`, `iscrowd=0`. Les IDs numériques sont attribués
dans l'ordre des pages fourni et l'ordre des blocs de stockage, sans
collisions. L'objet supplémentaire `mille_feuilles_id_mapping` associe
chaque image et annotation aux IDs canoniques, sans détourner les champs
COCO. `autre` demeure classe 8 ; son adaptation en `texte` pour l'OLR
d'Axel appartient à l'adaptateur.

Chaque rapport déclare les champs non projetés : provenance, transforms,
empreinte/mode/dpi de l'image, profil et extensions arbitraires ; PAGE
perd aussi la précision subpixel ; COCO omet en plus articles, ordre,
lignes, mots et langue. Tous restent dans le JSON canonique conservé à
côté des exports. Les métadonnées personnalisées ci-dessus doivent être
lues pour retrouver les données que le vocabulaire natif ne définit pas.

Les tests emploient une fixture indépendante avec un titre sur deux
lignes, deux espaces consécutifs, accents, `ſ`, `ﬁ`, `œ`, une césure
interbloc, des ordres de stockage volontairement inversés, les huit
catégories, des coordonnées fractionnaires et un polygone triangulaire.
Des altérations XML conformes au XSD et des altérations COCO contrôlent
que la relecture rejette effectivement les pertes sémantiques.
