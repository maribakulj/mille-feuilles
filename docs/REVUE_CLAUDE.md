# Revue critique de Claude — Mille Feuilles 0.2.0

Revue indépendante du 7 octobre 2026, Claude (Herdr `w8:p2`), à la demande
de Marcel et en coordination avec Codex (`w8:p1`). Elle porte sur le commit
documentaire `a135961` ; le code est inchangé depuis `0d1e2b7`. Le code du
moteur et des exporteurs a été lu sans modification ; aucune commande Git
n'a été exécutée en écriture. Les vérifications ont lu `runs/pilot-v0.2-r2`
sans y écrire.

## Vérifié sans défaut

- **Sens de la rotation** (`render.py:463-483`). Sur `mf_0003` (−0,115°),
  110 mots situés près des coins contiennent 25 293 pixels d'encre dans les
  boîtes publiées, contre 21 993 si la rotation était appliquée dans l'autre
  sens. La matrice correspond bien à `Image.rotate`.
- **Lignes consécutives** : aucun chevauchement de polygones dans un même
  bloc sur `mf_0003` (0 sur 446 paires ; ligne de 25,0 px, interligne de
  26,2 px).
- **Validateur** : aucun faux positif constaté, aucune violation du contrat
  0.2.0 trouvée.

## C1 — Limite aval : lecture des exports PAGE par le lecteur d'Axel

Il ne s'agit pas d'un défaut de l'export. Le profil PAGE 2019 de Mille
Feuilles (type natif, `custom` en JSON, conteneur `c_<id>` sous
`AdvertRegion`) est documenté dans [EXPORTS.md](EXPORTS.md) ; un adaptateur
aval est prévu. Le lecteur `axel.olr.page.load_page` suit les conventions
NewsEye/Transkribus (`custom="structure {type:heading;}"`, ordre limité aux
`TextRegion`). Sur `exports/page/mf_0003.xml` :

| Information canonique | Lue par Axel |
|---|---|
| 26 blocs `titre` | 0 titre : tous lus `texte` |
| Article de chaque ligne | 0 ligne sur 535 avec un article |
| 14 annonces aux rangs 3, 4, 24, 32… | rejetées aux rangs 75, 76, 77… |

Aucune erreur n'est signalée : une mesure d'OLR ou d'ordre de lecture faite
directement sur ces exports serait faussée. Reproduction, en lecture seule :

```sh
PYTHONPATH=~/axel/src uv run --locked python -c "from pathlib import Path; \
from collections import Counter; from axel.olr.page import load_page; \
pg = load_page(Path('runs/pilot-v0.2-r2/exports/page/mf_0003.xml')); \
print(Counter(b.type for b in pg.blocks), Counter(b.article for b in pg.blocks))"
```

Aucun autre lecteur PAGE (kraken, outils PRImA…) n'a été essayé ; rien n'est
affirmé à leur sujet. Décision commune : pas de modification d'Axel, pas
d'export générique dépendant d'Axel, ni de test qui dépende de `~/axel`. Un
test d'intégration accompagnera l'adaptateur, une fois son interface décidée.

## C2 — Formulation : dégradations très légères

Paramètres relevés sur les 100 pages du pilote (`provenance.parameters`) :

| Mode | Pages | Écart papier−encre (niveaux) | Flou max | Angle max |
|---|---|---|---|---|
| `clean` | 22 | 217–237 | 0 | 0° |
| `aged` | 50 | 206–229 | 0,30 px | 0,34° |
| `faint` | 28 | 158–182 | 0,29 px | 0,34° |

Le bruit est gaussien, d'écart-type 0,55, avec un dégradé de ±1,5 niveau
(`render.py:131-132, 443-448`). Le minimum de 74/255 mesuré par l'audit de
lisibilité est cohérent avec ces valeurs : le seuil de 40 n'a jamais été mis à
l'épreuve. Les intitulés « vieillies » et « encre faible » décrivent une
intention plus forte que le rendu. Ce n'est pas un bogue : VALIDATION.md
qualifie déjà les dégradations de légères.

## C3 — Provenance textuelle : contrôle ajouté

Avant la revue, `validate_dataset` vérifiait les bornes de `text_spans`, mais
jamais leur présence dans le texte composé. Codex a ajouté
`validate_text_provenance` (`validation.py`) : chaque segment déclaré doit
apparaître, sous forme de suite contiguë de mots, dans un article ou dans un
bloc sans article. Le texte est normalisé en NFC et par espaces ; seules les
césures annotées sont recollées. Ce contrôle établit une occurrence, pas une
attribution unique ni une couverture.

Les tests indépendants sont dans `tests/test_text_provenance.py` (24 cas) :
mauvais segment ou mauvais actif, mutations (accent, ponctuation, ordre,
insertion, suppression), spans titre/corps en ordre inverse, césure entre
blocs, tirets lexicaux et tiret suspendu, normalisation NFC et espaces, texte
de gabarit sans span, segments répétés. Ils couvrent aussi les assemblages
interdits entre deux articles ou entre un article et un bloc libre, ainsi que
l'ordre de stockage inversé. Deux cas portent sur une page réellement rendue :
l'une intacte ; l'autre avec une mutation de même longueur qui reste valide
pour `validate_page`.

Ces tests ont été éprouvés contre cinq versions fautives du helper : césures
non recollées, articles fusionnés en un seul flux, tiret final supprimé,
absence de normalisation NFC, inclusion d'ensemble au lieu d'une suite
contiguë. Chacune fait échouer au moins un test. Sur les 100 pages du pilote,
le helper ne signale aucune erreur pour 9 907 spans.

## Remarques mineures

- ALTO : `HypPart1` garde le « - » dans `CONTENT`, sans élément `<HYP/>`,
  selon la convention explicite de [EXPORTS.md](EXPORTS.md). Un consommateur
  qui attend `<HYP/>` devra l'adapter.
- `render.py:272` consomme des numéros de groupe de césure pour des articles
  abandonnés ensuite (`render.py:389`) : les identifiants `_hNNNNN` ne sont pas
  contigus. Sans gravité.
- `validate_dataset` ne compare pas `config.json["pages"]` à `manifest.pages`.
  Une page retirée du manifeste reste détectée par le décompte COCO.
