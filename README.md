# Mille Feuilles

Générateur autonome de pages de presse synthétiques avec **vérité de composition** :
articles, blocs, lignes, mots, baselines, ordre de lecture et provenance. Le moteur
produit des images PNG en gris, un JSON canonique et des exports **PAGE 2019,
ALTO 4.4 et COCO**, avec contrôles automatiques et planches de vérification.

Dépôt privé : [maribakulj/mille-feuilles](https://github.com/maribakulj/mille-feuilles).
Dossier de travail actuel : `~/heritage-synth`. Axel/ebortz/babaorum reste un
consommateur indépendant, sous sa propre coordination.

La version **0.3.0** ajoute l'import de plusieurs documents, leur partition avant
composition et une provenance exacte par article et bloc. La version 0.2.0
avait été éprouvée sur **100 pages** avec **227 tests** après la revue réciproque
Codex / Claude ; ses exports
sont validés et les 100 images/annotations ont été reproduites à l'identique.
Les [preuves et limites](docs/VALIDATION.md) distinguent cette validation
technique d'une évaluation sur des documents historiques réels.
L'acceptation du **lot 2**, en 0.3.0, a passé **483 tests**. Son essai CLI a importé
18 documents, en a exclu deux et a produit **trois pages**, une par partition,
avec reproduction du lot train à l'identique. Ces résultats restent les preuves
du lot 2. Le **lot 3 est éprouvé** : **652 tests**, puis **224 contrôles** sur six
pages de référence, avec rejeu et reproduction identiques. Il ajoute des
dégradations déclarées, un masque d'encre idéale et une lisibilité mesurée par
heuristique. La revue de six miniatures et 17 extraits confirme aussi les
limites de ces étiquettes ; les [preuves](docs/VALIDATION.md) les détaillent.
Le **lot 4 est éprouvé** : 941 tests distincts réussis et 284 contrôles CLI sur
sept pages de référence, avec rejeu de deux pages et 45 fichiers identiques.
Il ajoute des zones, une bande équilibrée sous les titres larges et des annonces
encadrées. Ces résultats ne valident pas l'heuristique comme filtre OCR.

## Démarrer

Prérequis : Git et [uv](https://docs.astral.sh/uv/). L'exécution se fait depuis
un checkout du dépôt, avec Python 3.12 et les dépendances verrouillées.

```sh
git clone https://github.com/maribakulj/mille-feuilles.git
cd mille-feuilles
uv sync --locked --python 3.12
uv run --locked mille-feuilles generate --output runs/demo --pages 1
uv run --locked mille-feuilles validate runs/demo
```

La génération est locale, sur CPU, sans modèle OCR, clé d'API ou téléchargement
à l'exécution. Une destination non vide est refusée. En cas d'échec, conserver
le dossier pour diagnostic et choisir une nouvelle destination.

## Produire un lot

```sh
# Profil pilote : 100 pages, mélange de 4–6 colonnes, 2680 × 3698 px à 150 dpi.
uv run --locked mille-feuilles generate --output runs/pilote \
  --pages 100 --seed 20261007 --jobs 2

# Essai compact et propre, sans dégradations.
uv run --locked mille-feuilles generate --output runs/essai \
  --pages 2 --width 1200 --height 1656 --dpi 67 \
  --columns 5 --degradation clean --seed 127
```

Modes : `clean`, `aged`, `faint`, `mixed`. `aged` ajoute une légère teinte au
papier et `faint` réduit modérément le contraste ; ces noms ne désignent pas une
simulation de presse fortement dégradée. Ces deux modes partagent un bruit très
faible, un flou ≤ 0,3 px et une rotation d'au plus 0,35° (0,34° observé sur le
pilote). Chaque page possède une graine dérivée
de son index : le nombre de workers ne change pas son contenu. Le profil emploie
Pillow/FreeType BASIC, du français NFC, des fontes OFL épinglées et les mêmes
mesures pour dessiner et annoter chaque mot. Les dégradations photométriques et
la rotation sont consignées ; les coordonnées désignent l'image finale.

Une page pleine résolution représente environ 19 Mo avec ses annotations,
exports et planche QA ; prévoir de l'ordre de 2 Go pour 100 pages et de la marge.
Le générateur vérifie l'espace libre avant de démarrer. Les lots sont hors Git.

## Profils mesurés du lot 3

Le choix se fait avec **`--degradation-profile`** : `identity`, `controlled-v1`
ou le chemin d'un profil JSON. Cette option remplace les anciens modes
photométriques pour ce rendu. Les profils livrés portent `calibrated: false` :
leurs paramètres ne sont pas calibrés sur des pages historiques réelles.

```sh
uv run --locked mille-feuilles generate --output runs/mesure \
  --pages 1 --width 800 --height 1100 --columns 4 --seed 127 \
  --degradation-profile controlled-v1
```

`identity` est une **identité photométrique** : la rotation géométrique commune
à l'image et aux annotations reste appliquée. Pour choisir le suréchantillonnage,
renseigner `oversampling: 1` ou `2` dans le même fichier JSON ; il n'existe pas
de second drapeau CLI pour ce facteur. Exemple à enregistrer dans
`profils/identity-x2.json` :

```json
{
  "format": "mille-feuilles-degradation-profile",
  "version": "1",
  "name": "identity-x2",
  "description": "Identité photométrique avec rendu suréchantillonné.",
  "calibrated": false,
  "oversampling": 2,
  "families": {}
}
```

Passer ensuite `--degradation-profile profils/identity-x2.json` à la commande de
génération. Le ×2 dessine sur une grille double, puis réduit la couverture grise
avant le masque et les effets photométriques. L'image, les annotations et les
paramètres d'effets en pixels désignent la résolution finale. Ce mode augmente
le coût mémoire ; la [campagne du lot 3](docs/VALIDATION.md) mesure environ
20 s par page à taille pilote, exports et validation inclus, et un maximum RSS
cumulé des enfants de 1,12 Go sur la machine de mesure.

Ces pages utilisent **`fr_press_19c_columns_4_6_measured`**, toujours en schéma
**0.3.0**. À paramètres de composition, sources, graine et facteur identiques,
deux profils mesurés conservent la même composition, la même géométrie et le même
masque idéal. Cette comparaison ne s'étend pas aux facteurs ×1/×2 différents.
Sans profil mesuré, les PNG et annotations des modes existants gardent leurs
octets dans l'environnement verrouillé ; l'environnement et le manifeste
continuent de décrire le code effectivement utilisé.

Le profil est copié dans `provenance/degradation-profile.json`, inventorié et
conservé dans la configuration. Chaque page ajoute un masque idéal **PNG 1 bit**
dans `qa/masks/` et des diagnostics dans `qa/diagnostics/`, avec références et
empreintes. Le validateur recalcule les mesures à partir de l'image finale, du
masque et des polygones. Le [contrat](docs/CONTRAT_DONNEES.md#41-profil-mesuré-et-diagnostics)
décrit ces références ; les [effets et seuils](docs/DEGRADATIONS.md) sont versionnés.

Les étiquettes **`heuristic-v1`** autorisent `readable`, `uncertain` et
`illegible` dans ce profil. Le profil historique continue d'exiger `readable`.
Une étiquette heuristique `readable` **ne certifie pas une supervision OCR
valable** : des lettres partiellement effacées peuvent conserver assez d'encre
pour passer les seuils. Le contrôle d'occupation du masque dans les blocs ne
reconstruit pas les glyphes ; un masque falsifié puis réempreinté peut rester
compatible avec ces zones. La relecture visuelle et la reproduction conservent
donc leur rôle dans l'acceptation.

## Mise en page par zones — lot 4

Le profil `fr_press_19c_layout_v2` ajoute un rez-de-chaussée à colonnage distinct,
un titre large avec son article réparti sur les colonnes couvertes, des corps
par article et des annonces encadrées. Il exige un profil de dégradation
explicite ; `identity` permet de contrôler la composition.

```sh
uv run --locked mille-feuilles generate --output runs/mise-en-page-v2 \
  --pages 2 --width 1200 --height 1656 --columns 4 --seed 20261007 \
  --layout-profile fr_press_19c_layout_v2 --degradation-profile identity
```

`--columns` fixe seulement la zone principale. Les choix sont déclarés dans
`template_press_v2` avec `calibrated: false`. Le plan, les fontes par zone et les
réservations des articles sont conservés dans le canonique. Les statistiques
rapportent les structures effectivement produites, les corps et les hauteurs
de ligne. Les [règles de mise en page](docs/MISE_EN_PAGE.md) précisent les rejets
contrôlés quand les textes ne tiennent pas. La [campagne finale](docs/VALIDATION.md)
couvre les facteurs ×1/×2, les exports, le rejeu et les profils antérieurs.
Les probabilités de tirage ne sont pas une calibration historique ; les petits
corps dégradés montrent aussi que `heuristic-v1` ne convient pas comme seul
filtre de supervision OCR.

## Lire et vérifier le résultat

- `images/` et `pages/` : PNG et JSON canonique de chaque page.
- `exports/page/`, `exports/alto/`, `exports/coco/` : projections selon les
  [profils documentés](docs/EXPORTS.md), avec métadonnées complémentaires.
- `exports/reports/` : correspondances d'identifiants et informations non
  représentables directement dans les formats d'export.
- `qa/` : contours, baselines, identifiants/ordre des blocs, planches de contact,
  statistiques et `report.json`.
- `manifest.json`, `assets.json`, `config.json`, `environment.json` : paramètres,
  actifs, versions, empreintes et provenance ; `calibration/` conserve les relevés
  hérités sans relire les corpus réels.

Le lecteur PAGE actuel d'Axel attend des conventions NewsEye différentes :
sans adaptateur, il perd le type des titres, les articles et le rang des annonces.
La validation du format ne garantit pas l'interprétation par tout lecteur.
Une projection supplémentaire [PAGE NewsEye](docs/EXPORT_NEWSEYE.md) applique
des conventions explicites, éprouvées par un lecteur indépendant. La lecture
par Axel lui-même reste à vérifier sous sa propre coordination.

```sh
uv run --locked mille-feuilles export-newseye --from runs/pilote \
  --output runs/pilote-newseye --page mf_0003
uv run --locked mille-feuilles validate runs/pilote-newseye
```

La commande valide tout le lot source, puis copie les pages sélectionnées dans
une destination neuve et séparée, sans nouveau rendu. Les XML à la racine
référencent les PNG copiés dans `images/` ; les JSON canoniques conservés dans
`provenance/pages/` permettent de retrouver les informations non projetées.
Sans `--page`, toutes les pages sont sélectionnées (plafonds : 100 pages,
200 Mo, réserve de disque de 500 Mo). Le validateur autonome recoupe le XML,
les images et le canonique ; le contrôle complet de la source est un reçu
archivé, sans nouvelle vérification des textes et droits absents du bundle.

Pour un lot natif, `validate` contrôle les schémas JSON, références et géométries, spans Unicode,
césures, fichiers et SHA-256, preuves de droits, PNG, XSD et relecture des exports.
En 0.3.0, chaque segment source désigne son article et ses blocs ordonnés ; leur
texte reconstruit doit lui être exactement égal après normalisation NFC, des
espaces et reconstruction des césures. Le bandeau est vérifié contre le texte du
gabarit. Les anciens lots 0.2.0 gardent leur contrôle d'occurrence moins strict.
Il sort avec un code non nul dès qu'un contrôle échoue. `qa/report.json` est le
résultat de l'audit, exclu des empreintes pour éviter une référence circulaire ;
une nouvelle commande `validate` recalcule les contrôles.

Pour vérifier une reproduction complète, générer dans deux répertoires neufs
avec les mêmes paramètres, actifs, versions et sources, puis :

```sh
uv run --locked mille-feuilles compare runs/lot-a runs/lot-b
```

La comparaison valide les deux lots, puis compare chaque artefact et le manifeste
bit à bit. L'environnement et le commit sont compris : revenir au commit de
production pour reproduire un ancien lot. Les sources Python, schémas et versions
utilisées sont enregistrés dans l'environnement.

Les outils d'acceptation ajoutent un contrôle des pixels de tous les mots et
une reproduction séquentielle des images et JSON canoniques du pilote :

```sh
uv run --locked python tools/audit_legibility.py runs/pilote \
  --report runs/pilote-lisibilite.json --samples-dir runs/pilote-mots
uv run --locked python tools/reproduce_pilot.py runs/pilote \
  --output runs/pilote-reproduction --report runs/pilote-reproduction.json
```

Choisir des sorties neuves. Les copies sont conservées. La mesure de contraste
ne remplace pas la lecture visuelle ; les seuils, échantillons et limites sont
définis dans le [protocole d'acceptation](docs/VALIDATION.md).

## Comparer la structure de pages existantes

Le rapport A1 applique les définitions du cadrage aux JSON canoniques sélectionnés,
puis les compare aux relevés agrégés déjà archivés. Il lit le manifeste et ces
annotations ; les images, actifs, textes sources et exports ne sont pas revérifiés.
Il ne rouvre aucun corpus historique.

```sh
uv run --locked mille-feuilles report-structure --from runs/mise-en-page-v2 \
  --output runs/structure-v2 --page mf_0000 --page mf_0001 \
  --reference as:XIXe
```

Choisir explicitement les pages avec `--page`, ou toutes avec `--all-pages`.
La destination neuve contient `report.json` et `report.sha256`. Le rapport
conserve les observations par page, leurs agrégats, les empreintes des entrées
et les limites de comparaison. La cohorte `as:XIXe` regroupe 53 pages train et
12 dev ; ses quantiles ne permettent pas de reconstruire des sous-cohortes.
La commande est bornée à 100 pages, 200 Mo de JSON canoniques et 20 Mo de
sortie, avec une réserve de disque de 500 Mo.

La variante principale conserve le bandeau. L'analyse de sensibilité le retire
seulement lorsque toutes les pages sélectionnées l'identifient ; sinon cette
variante est déclarée indisponible pour la cohorte, avec observations partielles.
Les statuts C/A/NC/ND distinguent équivalence, approximation, non-comparabilité
et absence de mesure. Les pixels ne sont pas comparés entre résolutions et les
unités physiques ne sont pas mesurées. Un calcul réussi ne constitue ni un
verdict de réalisme ni une preuve de gain OCR. Les
[définitions et limites](docs/REALISME_STRUCTUREL.md) précisent cette portée.

## Utiliser d'autres textes

Un manifeste JSONL décrit un document par ligne, ses droits, sa preuve locale,
son rôle (`body`, `title`, `advertisement`), son identifiant documentaire unique
et son groupe source. Le [format et les exclusions](docs/ACTIFS.md#import-local-de-plusieurs-documents-catalogue-030)
sont documentés avec leurs limites. Plusieurs documents par rôle sont permis.

```sh
uv run --locked mille-feuilles import-texts --manifest entree/import.jsonl \
  --into runs/bundle --exclude-documents entree/exclusions.txt \
  --exclude-ngrams entree/ngrams.json
uv run --locked mille-feuilles partition --bundle runs/bundle \
  --ratios 0.8 0.1 0.1 --seed 20261007
uv run --locked mille-feuilles generate --assets-root runs/bundle \
  --partition train --output runs/train --pages 1
```

Les chemins sources restent dans le dossier du manifeste. L'import refuse les
droits non vérifiés, preuves manquantes, doublons d'identifiant ou de contenu,
textes non NFC et glyphes manquants. Les fontes requises Old Standard Regular et
Bold et leurs licences sont embarquées. Un mot non sécable trop large est refusé
à la composition. Les corps et annonces sont séparés par une ligne vide ; les
titres par un saut de ligne. Le tirage est uniforme sur les unités disponibles :
un document qui en contient davantage est donc sélectionné plus souvent.

Les groupes qui partagent une unité textuelle normalisée restent ensemble.
Chaque partition de ratio positif doit posséder les trois rôles. Les ratios
sont des objectifs : les composantes indivisibles peuvent empêcher de les
atteindre exactement. Le catalogue de démonstration 0.2.0 reste lisible, mais
ses trois textes forment un seul groupe, impropre à une séparation train/dev/test.

Dès qu'un plan existe, **`--partition` est obligatoire**. Le lot copie uniquement
les textes sélectionnés. Son reçu conserve le plan et le catalogue source complet :
les identifiants, URI et empreintes dev/test sont donc visibles, sans leurs textes.
Le rapport d'import est également conservé. Sans les deux listes d'exclusion,
la protection contre des tests externes est marquée **NOT EVALUATED**. Même avec
elles, le résultat porte seulement sur les exclusions fournies ; aucun jeu réel
d'Axel n'a été certifié par notre essai.

Un lot filtré peut servir de `--assets-root` pour un rejeu avec la même
`--partition`. Ses métadonnées et textes sélectionnés sont vérifiés sans ouvrir
les textes des autres partitions. Recalculer le graphe complet exige le bundle
source complet. Voir les [preuves et limites](docs/VALIDATION.md).

## Portée et limites

Les textes embarqués sont des démonstrations originales sous CC0, **pas un corpus
historique**. Le profil couvre texte, titres, annonces et filets, césures et
articles entre colonnes. Les schémas/exporteurs savent représenter d'autres
catégories, mais ce moteur ne génère pas encore tableaux, illustrations, lettrines,
courbures ou textes complexes non latins. Les modes historiques restent légers ;
les profils mesurés peuvent produire des mots dégradés, signalés par les
étiquettes et diagnostics avec les limites décrites ci-dessus.
Les césures sont choisies selon la largeur disponible, sans dictionnaire de
syllabification ; leur reconstruction textuelle est contrôlée.

Le contrat et le cadrage ne doivent pas être confondus avec une preuve de
représentativité historique. Les contrôles garantissent la cohérence du lot dans
leur périmètre ; aucun gain d'OCR, de segmentation ou d'ordre de lecture sur le
réel n'est revendiqué. Une telle expérience doit être organisée avec Axel sur un
test gelé et avec des actifs appropriés. Le pilote ne consomme aucune page de test.

Les fontes conservent leurs licences OFL ; les textes originaux leur dédicace CC0.
Ces licences ne constituent pas une licence générale du code du projet privé.

## Développer et retrouver les décisions

```sh
uv run --locked pytest -q
uv run --locked ruff check src tests
uv run --locked python assets/verify_assets.py
```

- [Contrat 0.3.0](docs/CONTRAT_DONNEES.md) et [décisions](docs/DECISIONS.md).
- [Développement en cours et prochains lots](docs/DEVELOPPEMENT.md).
- [Protocole et preuves de validation du pilote](docs/VALIDATION.md).
- [Revue critique de Claude](docs/REVUE_CLAUDE.md).
- [Cadrage reçu de Claude](docs/CADRAGE.md), fondé sur 1 253 pages train/dev.
- [Actifs et licences](docs/ACTIFS.md), [exports](docs/EXPORTS.md),
  [dégradations mesurées](docs/DEGRADATIONS.md), [revue indépendante du rendu](docs/REVUE_RENDU.md).
- [Coordination et passation](docs/COORDINATION.md),
  [passation Codex Axel](docs/PASSATION_CODEX.md), [journal](docs/JOURNAL.md).

Les relevés de calibration et notes de passation conservent leurs chemins locaux
historiques. Les corpus et vignettes réels ne sont pas incorporés au dépôt.
