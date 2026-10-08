# Composition du corps par unités consécutives

`content_profile='consecutive-v1'` est un preset expérimental non calibré. Il
change la sélection du texte et conserve la mise en page
`fr_press_19c_layout_v2`. Il exige ce layout et son profil de dégradation
explicite, dont `identity`. Son activation CLI est `--content-profile
consecutive-v1` ; les profils antérieurs restent inchangés quand cette option
est absente. L'ajout du preset ne constitue pas une calibration historique.

## Sélection et placement

Le preset tire successivement :

1. Un document de rôle `body`, uniformément parmi ceux qui possèdent au moins
   deux unités. Les documents sont indexés par ID d'actif trié.
2. Un nombre d'unités, uniformément parmi 2 et 3 disponibles dans ce document.
3. Un début, uniformément parmi les fenêtres complètes de ce nombre d'unités.

Le nombre est tiré même lorsqu'il ne peut valoir que deux. Tous les tirages
utilisent le générateur local de la page ; aucun état aléatoire global ni curseur
partagé entre workers n'intervient. Le nombre d'unités n'est jamais réduit pour
faire tenir un candidat. Un nouveau candidat indépendant peut être proposé après
un rejet entier ; aucun retour à une seule unité n'est permis. Le placement peut
donc biaiser la distribution des articles effectivement retenus : les tirages
uniformes ne garantissent pas une distribution uniforme des articles composés.

Le rendu v2 prépare le corps complet avant de le placer dans une ou plusieurs
colonnes de sa zone. Le corps sous un titre large suit la même sélection et les
règles de sa bande équilibrée. Au moins un article de corps multiunités doit
être effectivement composé sur chaque page. Les annonces gardent leur sélection
existante. Aucun article ne continue sur une autre page et aucune fenêtre n'est
tronquée après un échec de placement. Une réserve de place insuffisante peut
provoquer un refus explicite malgré un préflight textuel réussi.

## Texte et provenance

Les unités proviennent exactement de `catalog.text_units(raw, 'body')` dans
l'ordre du document. Elles correspondent au découpage existant du catalogue ;
aucune seconde logique de paragraphes n'est ajoutée. Deux documents partageant
un groupe ne peuvent pas être joints. Des textes identiques dans des documents
distincts restent des entrées distinctes ; des unités identiques conservent
leurs propres positions.

Pour une fenêtre `[i,j)`, le corps est la tranche
`raw[units[i].start:units[j-1].end]`. Elle inclut les séparateurs originaux entre
unités. `raw` est le texte UTF-8 NFC décodé avec la conversion universelle des
fins de ligne de `Path.read_text` : CRLF et CR deviennent LF. Les indices sont
des positions Unicode dans cette représentation, pas des offsets d'octets. Le
SHA-256 de l'actif porte toujours sur ses octets originaux, avant conversion.
Le préflight vérifie puis décode les mêmes octets en mémoire.

Un seul span de source porte tout le corps et tous ses blocs, dans leur ordre de
lecture. Il garde la propriété unique de chaque bloc et celle des fragments de
césure intercolonne. L'extension d'article réservée est :

```json
{
  "mf:source_sequence": {
    "version": "1",
    "asset_id": "identifiant-actif",
    "start": 0,
    "end": 42,
    "unit_range": [0, 2]
  }
}
```

Les bornes illustrées ne définissent aucun texte réel. Le validateur doit
raccorder cette extension à l'unique span de corps de l'article, recalculer les
unités sur le document sélectionné et vérifier les bornes exactes. La
reconstruction normalisée du texte et les contrôles des césures restent requis.

Le titre reste sélectionné séparément et peut provenir d'un autre document.
La garantie d'origine commune concerne le **corps**, pas l'article entier.
Le compositeur aplatit les espaces avec `text.split()` : les séparateurs sont
traçables dans la source, mais les blancs et retraits typographiques des alinéas
ne sont pas conservés. Ce preset ne promet pas une reconstitution de paragraphes
historiques ni une cohérence sémantique entre le titre et le corps.

## Préflight et API

`index_body_documents(documents)` est pur. Il reçoit une liste de couples
`(asset, texte décodé)`, calcule les unités et retourne `documents` avec les seuls
corps éligibles, ainsi qu'un `report` compact. `choose_body_sequence(index, rng)`
est pur et retourne `source`, `text`, `start`, `end` et `unit_range`. Le premier
helper exige un texte déjà NFC et décodé avec fins de ligne universelles ; il ne
peut pas vérifier une empreinte d'octets sans ces octets.

`preflight_content(source_root, selected_text_assets, *, profile)` lit seulement
les actifs de corps fournis après sélection de la partition. Il vérifie les
chemins confinés, les SHA-256 et le NFC, puis appelle le helper pur. Les plafonds
existants du catalogue bornent ses lectures. Il ne lit aucun titre, annonce,
image, fonte ou texte exclu de la sélection, et n'écrit aucun fichier. Le pipeline
l'appelle avant de créer sa destination. Si aucun document n'a au moins deux
unités, il lève `ValueError` ; il ne prouve ni la validité des droits ni la
capacité géométrique de placement.

Le rapport version `1` contient `profile: 'consecutive-v1'`, `calibrated: false`
et une liste `documents` triée par `asset_id`. Chaque entrée contient
`asset_id`, `source_document_id`, `sha256`, `unit_count`, `eligible` et `reason`.
Le motif vaut `null` si le document est éligible, sinon
`fewer_than_two_body_units`. Les documents trop courts sont donc explicites
lorsqu'au moins un autre document est utilisable. Le reçu ne contient pas les
textes. Le rendu reconstruit son index à partir des copies vérifiées et le
rejeu recoupe les données de sélection archivées.

## Portée

Les preuves unitaires utilisent seulement des textes originaux minuscules :
Unicode, CRLF, doublons, fenêtres extrêmes, ordre de tirage, absence de mutation
du RNG global, chemins refusés et documents inéligibles. Aucun paramètre du
preset ne vient des quatre pages d'acceptation A1. La continuité et la longueur
des corps augmentent les possibilités du démonstrateur, sans enrichir son
corpus. Des unités consécutives d'un document ne prouvent pas qu'elles formaient
un article historique. Aucun gain d'OCR, de segmentation ou d'apprentissage
n'est démontré par cette capacité seule.
