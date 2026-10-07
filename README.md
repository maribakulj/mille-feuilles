# Mille Feuilles

Générateur autonome de pages de presse synthétiques avec **vérité de composition** :
articles, blocs, lignes, mots, baselines, ordre de lecture et provenance. Le moteur
produit des images PNG en gris, un JSON canonique et des exports **PAGE 2019,
ALTO 4.4 et COCO**, avec contrôles automatiques et planches de vérification.

Dépôt privé : [maribakulj/mille-feuilles](https://github.com/maribakulj/mille-feuilles).
Dossier de travail actuel : `~/heritage-synth`. Axel/ebortz/babaorum reste un
consommateur indépendant, sous sa propre coordination.

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

Modes : `clean`, `aged`, `faint`, `mixed`. Chaque page possède une graine dérivée
de son index : le nombre de workers ne change pas son contenu. Le profil emploie
Pillow/FreeType BASIC, du français NFC, des fontes OFL épinglées et les mêmes
mesures pour dessiner et annoter chaque mot. Les dégradations photométriques et
la rotation sont consignées ; les coordonnées désignent l'image finale.

Une page pleine résolution représente environ 19 Mo avec ses annotations,
exports et planche QA ; prévoir de l'ordre de 2 Go pour 100 pages et de la marge.
Le générateur vérifie l'espace libre avant de démarrer. Les lots sont hors Git.

## Lire et vérifier le résultat

- `images/` et `pages/` : PNG et JSON canonique de chaque page.
- `exports/page/`, `exports/alto/`, `exports/coco/` : projections interopérables.
- `exports/reports/` : correspondances d'identifiants et informations non
  représentables directement dans les formats d'export.
- `qa/` : contours, baselines, identifiants/ordre des blocs, planches de contact,
  statistiques et `report.json`.
- `manifest.json`, `assets.json`, `config.json`, `environment.json` : paramètres,
  actifs, versions, empreintes et provenance ; `calibration/` conserve les relevés
  hérités sans relire les corpus réels.

`validate` contrôle les schémas JSON, références et géométries, spans Unicode,
césures, fichiers et SHA-256, preuves de droits, PNG, XSD et relecture des exports.
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

## Utiliser d'autres textes

`--assets-root /chemin/bundle` choisit un bundle contenant `assets/catalog.json`
au format 0.2.0. Le catalogue livré constitue un exemple. Les chemins et preuves
restent sous `assets/`, avec SHA-256, droits vérifiés et licence embarquée.

Trois actifs texte sont requis, identifiés par `metadata.role` : `body`, `title`,
`advertisement`. Leurs noms de fichiers sont libres. Les corps et annonces sont
séparés par une ligne vide ; les titres par un saut de ligne. Chaque actif porte
un `metadata.source_document_id`. Les fontes Old Standard Regular et Bold sont
requises par ce profil. Un texte non NFC, un glyphe absent ou un mot non sécable
trop large est refusé. Le catalogue d'origine est conservé dans le lot ; un lot
livré peut servir de `--assets-root` pour réutiliser ses actifs figés.

## Portée et limites

Les textes embarqués sont des démonstrations originales sous CC0, **pas un corpus
historique**. Le profil couvre texte, titres, annonces et filets, césures et
articles entre colonnes. Les schémas/exporteurs savent représenter d'autres
catégories, mais ce moteur ne génère pas encore tableaux, illustrations, lettrines,
courbures ou textes complexes non latins. Les dégradations restent légères.
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

- [Contrat 0.2.0](docs/CONTRAT_DONNEES.md) et [décisions](docs/DECISIONS.md).
- [Protocole et preuves de validation du pilote](docs/VALIDATION.md).
- [Cadrage reçu de Claude](docs/CADRAGE.md), fondé sur 1 253 pages train/dev.
- [Actifs et licences](docs/ACTIFS.md), [exports](docs/EXPORTS.md),
  [revue indépendante du rendu](docs/REVUE_RENDU.md).
- [Coordination et passation](docs/COORDINATION.md),
  [passation Codex Axel](docs/PASSATION_CODEX.md), [journal](docs/JOURNAL.md).

Les relevés de calibration et notes de passation conservent leurs chemins locaux
historiques. Les corpus et vignettes réels ne sont pas incorporés au dépôt.
