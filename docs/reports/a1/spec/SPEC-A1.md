# A1 — Rapport structurel « Mille Feuilles contre relevés agrégés du cadrage » (spécification, sans code)

Statut : **révision 2, FIGÉE** après l'audit complet de Codex (`review-a1-calibration.json`) ; méthode tranchée par Codex (appel épinglé). Aucun code avant son signal. Aucune écriture dans le dépôt avant la fin du lot 5. Périmètre resserré par Codex :
- rapport **autonome** ; aucun changement de rendu, de génération ni de validation des lots existants ;
- **aucune** prétention de gain ni de réalisme global ;
- A2 non engagé.

Entrées autorisées : `tools/cadrage/sortie/calibration.json` (agrégé, versionné) et les **pages canoniques
JSON** de lots Mille Feuilles. `tools/cadrage/calibrer.py` est **lu**, jamais exécuté (ni `main`, ni accès à
ses manifestes ou à ses corpus).

## 1. Audit des définitions de `calibrer.py`
Les citations renvoient aux lignes du fichier au commit `7c88927`.

**Agrégation (l. 693–705).**
- Chaque mesure par page s'ajoute à des listes indexées par `source` et `source:époque`.
- `q()` (l. 277) donne n, moy, p10, p25, p50, p75, p90, min et max, avec
  `statistics.quantiles(n=20, method="inclusive")` et un arrondi à 4 décimales.
- Les comptes par catégorie donnent `valeur` et `part` (l. 702).
- **Train et dev sont regroupés** dans `stats` : la clé n'inclut pas le split. Seuls `pages[]` (avec
  `split` et `colonnes`) et `pages_par_source_split_epoque` les distinguent. Pour `as:XIXe`, n = 65 pages,
  soit 53 train et 12 dev.

**Typage (`type_blocks`, l. 231, règle D-231).**
- `annonce` si au moins la moitié de la TextRegion est couverte par une AdvertRegion, par découpage selon
  la **boîte englobante** de l'AdvertRegion (`covered`, l. 222) ;
- sinon `tableau` ;
- sinon `titre` (`heading`), `legende` (`caption`), `autre` (en-tête, pied, folio, etc.) ;
- sinon `texte`.

**Mesures (`mesurer`, l. 342).** La plupart reposent sur des boîtes englobantes alignées sur les axes
(AABB), avec trois **exceptions** :
- les **surfaces** sont des aires polygonales (shoelace, `area`) ;
- l'**ordonnée d'une baseline** est la **moyenne des y de tous ses points** (`baseline_y`, l. 330), et non
  le bas de l'AABB, sauf en l'absence de baseline ;
- la **largeur d'une colonne** est la statistique d'ordre `widths[floor(0,75 × (n − 1))]` des largeurs
  triées du groupe (l. 316). Elle diffère du quartile interpolé de `q()` : pour [1, 2, 3, 100], elle vaut 3
  au lieu de 27,25.
- **Filets** : vertical si h > 3w, horizontal si w > 3h.
- **Marges** : enveloppe de **tous** les blocs typés.
- **Colonnes** (`columns`, l. 290) : regroupement des bords gauches des lignes des blocs `texte` dont la
  largeur est au plus 0,45 × la largeur de l'enveloppe du texte. Les groupes sont à 1,5 % de W, gardés s'ils
  pèsent au moins 4 %, fusionnés sous 6 % de W. Largeur = 3e quartile des largeurs.
- **Lignes** (blocs `texte` seulement) :
  - hauteur = hauteur de l'AABB ;
  - pas = écart des moyennes y des baselines de lignes consécutives d'un même bloc dont les x0 diffèrent de
    moins de 0,3 × la largeur ;
  - signes = `len(text.strip())` ;
  - césure : le texte se termine par l'un de `¬ - ⸗ ‐ =`.
- **Articles** : l'article de chaque bloc ordonné non séparateur est celui de la majorité de ses lignes ; un
  article est une annonce si au moins la moitié de ses blocs le sont. Une **largeur de titre** supérieure à
  1,5 × la médiane des colonnes compte comme titre sur plusieurs colonnes.
- **Transitions d'ordre** entre blocs successifs (AABB).
- **Grandeurs physiques** (cm, mm, pt) seulement si le dpi d'image vaut au moins 200.

**Agrégation et données manquantes (`q`, l. 277).** Les NaN sont filtrés. n = 0 donne `{n: 0}` ; n = 1
donne `{n: 1, p50}`, **sans** p10 ni p90. Les **comptes par catégorie** (`blocs_nombre`, `blocs_surface`,
`ordre_transitions`) ont une branche à part, `valeur` et `part`, où part = valeur / somme de la cohorte :
pas de médiane, pas de n inventé. Une clé absente de `stats` **ne vaut pas zéro**. Les unités
d'échantillonnage diffèrent (page, colonne, gouttière, ligne de titre, article, filet, transition) : le
rapport expose unité et n par indicateur.

## 2. Statut de chaque indicateur pour Mille Feuilles
Légende :
- **C** = comparable : même code, entrée équivalente ;
- **A** = approximé : même code, mais une différence d'entrée connue ;
- **NC** = calculable, mais non comparable parce que la sémantique des catégories diffère ;
- statut **dynamique** : un indicateur absent d'un côté devient ND ; avec n = 1 d'un côté (pas de p10 ni de
  p90), il est **non comparé** ;
- **ND** = non disponible ou non pertinent.

| Indicateur(s) | Statut | Raison |
|---|---|---|
| `filets_par_page`, `filets_verticaux/horizontaux_par_page`, `filet_vertical_longueur_rel_H` | C | séparateurs canoniques → SeparatorRegion |
| `marge_*_rel_W/H`, `zone_imprimee_largeur_rel_W`, `page_rapport_H_sur_W` | C | même enveloppe de blocs (bandeau compris, comme le seraient les régions réelles) |
| `colonnes`, `colonne_largeur_rel_W`, `gouttiere_rel_W`, `gouttieres_avec_filet_part`, histogramme des colonnes | C | **même algorithme** sur les polygones canoniques, et non le colonnage déclaré du plan |
| `ligne_hauteur_rel_H_med_page`, `interligne_rel_H_med_page`, `largeur_colonne_sur_interligne` | C | relatifs, sans unité |
| `ligne_hauteur_px_med_page`, `interligne_px_med_page` | **A** | pixels non comparables entre résolutions (Mille Feuilles 67 ou 150 dpi déclarés, AS environ 300 dpi) ; rapportés, **pas comparés** |
| `caracteres_par_ligne_med_page`, `cesure_fin_de_ligne_part` | C | blocs `texte` seulement, même jeu de tirets ; la césure visible `-` de Mille Feuilles est conservée |
| `titre_sur_texte_hauteur_ligne`, `titre_ligne_sur_corps_texte` | C | même rapport d'AABB |
| `articles_par_page`, `article_*` (sauf mention), `annonce_lignes`, `annonce_caracteres`, `annonce_blocs`, `annonce_colonnes_occupees`, `annonce_contigu_dans_ordre`, `titre_largeur_en_colonnes`, `titre_sur_plusieurs_colonnes` | **A** | le **bandeau** de Mille Feuilles est un article de gabarit ; on ignore si le bandeau AS porte un article. Rapportés en deux variantes : avec et sans les blocs de gabarit (§ 4) |
| `annonce_avec_titre` | **NC** (non comparable dans cette sémantique) | il exige un bloc de catégorie `titre` dans un article majoritairement d'annonces. Mille Feuilles catégorise l'en-tête d'une annonce en `annonce`, et non en `titre` : un 0 côté Mille Feuilles **n'est pas** une absence visuelle de titre. Rapporté, jamais comparé ; aucune correction de modèle (A2) n'en est déduite (constat de l'agent de Codex) |
| `blocs_nombre`, `blocs_surface` | **A** | Mille Feuilles : catégories canoniques projetées puis retypées par D-231 ; réel : régions annotées à la main. Pas d'union géométrique : les recouvrements comptent plusieurs fois, des deux côtés |
| `autre` canonique (non produit par les profils actuels) | **A propagé** | `autre` est projeté en TextRegion de structure vide, donc lu `texte` par D-231. Si une page de la cohorte MF en contient, **toutes** les métriques influencées par les blocs `texte` passent en A pour ce rapport : colonnes, largeurs, gouttières, hauteurs, interlignes, signes, césure, colonne/interligne. La raison est inscrite. |
| bloc `tableau` canonique | **refus** | `RealismError("table_block")` en A1 : pas de conversion silencieuse en TableRegion |
| `ordre_transitions` | C | même classification AABB |
| `printspace_*` | ND | Mille Feuilles n'a pas de PrintSpace |
| `page_*_cm`, `colonne_largeur_cm`, `gouttiere_mm`, `interligne_pt_med_page`, `ligne_hauteur_mm_med_page` | ND | **arbitrage de Codex** : `dpi=None` est **toujours** passé à `mesurer` en v1 ; le DPI déclaré de Mille Feuilles est rapporté en métadonnée seulement. Côté réel, ces mesures ne couvrent que 35 pages AS et 44 pages READ |
| `interligne_estime_rel_H_med_page`, `kb_*` | ND | propres aux pages sans lignes (KB, BnF) |

**Cohorte de référence par défaut** : `as:XIXe`, train et dev **regroupés** (53 + 12 pages), puisque
`calibration.json` ne les sépare pas. On le déclare tel quel. Par page, `calibration.json` ne garde que
`colonnes` et des métadonnées (source, split, époque, titre, date, dpi). Seul l'histogramme des colonnes peut
donc être donné **par split**. **Aucune sous-cohorte** (train seul, pages à 4–6 colonnes, titre de journal)
n'est possible pour les autres distributions sans recalibration, c'est-à-dire sans relire les PAGE réels :
hors périmètre. `bnf:XIXe` et `read` peuvent être ajoutés en option ; ils n'ont pas d'articles.

**Polygones tournés** : géométrie **native** du JSON final, sans nouvelle rotation, sans plan avant
rotation et sans arrondi d'export. La même AABB est appliquée qu'aux scans réels, eux aussi inclinés. L'aire
shoelace est invariante par rotation, mais les AABB, marges, groupes de colonnes et décisions à seuil ne le
sont pas : une ligne de 300 × 18 px tournée de 0,35° a une AABB haute d'environ 19,83 px. L'angle de
Mille Feuilles est rapporté par page. Aucune variante dé-tournée ni arrondie en v1.

**Césure** : seule la règle de fin de texte de `calibrer.py` compte ; les groupes canoniques ne sont pas
utilisés.

## 3. Méthode recommandée : adaptateur et code de mesure épinglé
Pour garantir les **mêmes définitions** sans réécriture divergente :
1. `realism.py` construit, pour chaque page canonique, la structure `pg` qu'aurait produite
   `calibrer.parse_page` (l. 119) :
   - `width`, `height` ; `printspace=None` ;
   - `regions` : chaque bloc textuel donne une TextRegion (`struct` `heading` pour `titre`, `caption` pour
     `legende`, `None` sinon), avec ses `lines` (`poly` = polygone, `baseline`, `text`,
     `article` = `article_id` du bloc) ;
   - chaque `annonce` ajoute une AdvertRegion de même polygone ; `separateur` donne une SeparatorRegion,
     `illustration` une GraphicRegion ;
   - `order` = `reading_order.block_ids`, puis les non-ordonnés exclus comme dans la réalité ;
     `groups=[order]`.
2. **Décision de Codex (retenue).** `realism.py` charge `tools/cadrage/calibrer.py` sous un **nom de module
   propre** (`mille_feuilles._calibrer_cadrage`), par `importlib.util.spec_from_file_location`, **après**
   vérification de son SHA-256 contre `CALIBRER_SHA256`. Un SHA différent donne
   `RealismError("sha_calibrer")`, avant tout import.
   - **Autorisé**, en mémoire seulement : `mesurer`, `q` et leurs aides pures (`type_blocks`, `covered`,
     `clip_rect`, `area`, `bbox`, `columns`, `col_index`, `baseline_y`, et les intersections internes).
   - **Interdit** : `main`, `Journal` et `Journal.ouvrir`, `image_dpi`, `image_dpi_path`, `_head`, ainsi que
     tout accès à un fichier ou à un corpus.
   - L'import ne lance pas `main()` : la garde `__main__` a été relue par Codex. Il appelle les **fonctions
     de `calibrer.py` elles-mêmes**, `mesurer` et `q`, chargées depuis le fichier
   par `importlib`, après vérification de son **SHA-256 épinglé**. Un SHA différent est un refus. Seul
   `main()` exécuterait des lectures de fichiers ; il n'est jamais appelé.
3. L'agrégation reprend exactement les l. 699–705 (`q`, puis `valeur` et `part`).

Si Codex préfère ne pas dépendre de `tools/` depuis `src/`, l'alternative est une réécriture dans
`realism.py`, avec un **test d'équivalence** contre les fonctions de `calibrer.py` sur pages en mémoire.
Ma préférence reste l'appel épinglé : une seule définition.

## 4. Variantes et cohortes Mille Feuilles
- **Variante `avec_gabarit`** : toutes les régions.
- **Variante `sans_gabarit`** : les blocs des articles de gabarit (`provenance.extensions["mf:template_article_ids"]`)
  sont retirés de l'adaptateur. **Si la clé est absente** (pages 0.2.0 par exemple), la variante est **ND,
  identification du gabarit indisponible**, pour cette page : aucun retrait fictif. C'est une **analyse de sensibilité** au bandeau, **pas** une comparaison
  « plus vraie ». La variante `avec_gabarit` suit le **protocole historique** (toutes les régions, comme pour
  les pages réelles) et sert de comparaison principale. Les deux sont rapportées côte à côte.
- **Cohorte Mille Feuilles** : une liste explicite de pages canoniques. Chaque page est vérifiée par le
  SHA-256 du manifeste de son lot avant lecture. Le rapport donne profil, colonnage, oversampling et angle
  par page, ainsi que n par indicateur.

## 5. API proposée (`src/mille_feuilles/realism.py`)
```python
CALIBRER_SHA256 = "8b72e367424b6f8825539c46e349e2d948b942ff5412fd61a884fd4804ef820d"   # tools/cadrage/calibrer.py, inchangé depuis le cadrage
CALIBRATION_SHA256 = "6349af2f15c39f0203ffdf873b07d07454a8a3671bab9ee28b5b637ecf731c08"  # tools/cadrage/sortie/calibration.json
REAL_COHORT_DEFAULT = "as:XIXe"
INDICATOR_STATUS: dict[str, tuple[str, str]]  # nom -> ("C" | "A" | "ND", raison), table du § 2

def load_engine(calibrer_path: Path) -> ModuleType
    # SEULE fonction qui lit calibrer.py : vérifie CALIBRER_SHA256 puis importe sous
    # mille_feuilles._calibrer_cadrage ; sinon RealismError("sha_calibrer"), sans import
def load_reference(calibration_path: Path, cohort: str) -> dict
    # lit calibration.json après vérification de CALIBRATION_SHA256 ; refus "calibration" ou "cohort"
def canonical_to_pg(page: dict, *, include_template: bool = True) -> dict | None
    # adaptateur § 3.1 ; None si include_template=False et clé de gabarit absente (variante ND) ;
    # RealismError("table_block") pour un bloc tableau
def measure_pages(pages: list[dict], engine: ModuleType, *, include_template: bool = True) -> dict
    # SANS I/O : appelle engine.mesurer(pg, "mf", None, M, C, "XIXe") ; dpi toujours None ;
    # rapporte aussi les pages exclues de la variante et la raison
    # -> {"values": {nom: [floats]}, "counts": {nom: {cat: float}}} via calibrer.mesurer (§ 3.2)
def aggregate(measures: dict, engine: ModuleType) -> dict   # SANS I/O ; engine.q pour les listes,
    # branche valeur/part pour les comptes, exactement comme l. 699–705
def compare(mf_stats: dict, real_stats: dict, status=INDICATOR_STATUS) -> dict
    # par indicateur : statut, n_mf, n_reel, quantiles des deux côtés, position descriptive de la
    # médiane MF ("< p10", "p10–p90", "> p90", ou "non comparé" pour A/px et ND) ; aucun verdict
class RealismError(ValueError): code  # sha_calibrer, calibration, page, cohort
```
Le rapport complet (CLI chez Codex) contient : SHA de `calibration.json` et de `calibrer.py`, cohorte réelle
et ses n, liste des pages MF avec leurs SHA, les deux variantes, la table de statut et la mention
« contrôle descriptif, sans verdict de gain ni de réalisme global ».

## 6. Preuves (avant le code)
1. **Attendus écrits à la main** (`expected-fixture-1.json`) pour la page `tests/fixtures/newseye/fixture-1-order.json`
   (déjà commitée), dans les deux variantes : toutes les valeurs par page de `mesurer`, calculées à la main
   avec les définitions du § 1 (colonnes, pas, marges, articles, transitions, surfaces).
2. **Test d'équivalence** (si réécriture) ou **test d'épinglage** (si appel) : un SHA modifié est refusé ;
   l'adaptateur produit exactement la structure attendue.
3. **Agrégation** : sur trois listes écrites à la main, `aggregate` égale le format `calibration.json`.
4. **Comparaison** : position descriptive testée aux bornes (p10 et p90 inclus) ; A en px, NC et ND
   jamais comparés.
5. **Preuve de non-I/O pendant la mesure** :
   - pendant `measure_pages` et `aggregate`, `builtins.open`, `io.open`, `os.open`, `Path.open`,
     `Path.read_bytes`, `Path.read_text` et `Path.exists` sont remplacés par des fonctions qui échouent ;
   - le calcul doit réussir ;
   - un test témoin montre que ce piège déclenche bien sur un appel volontaire ;
   - les seules lectures autorisées ont lieu **avant** la mesure : `calibrer.py`, après vérification du SHA,
     `calibration.json`, après vérification du SHA, et les pages canoniques désignées.
6. **SHA** : copie altérée de `calibrer.py` dans `tmp_path`, d'un seul octet, refusée par `sha_calibrer` sans
   import ; de même `calibration.json` altéré, refusé par `calibration`.
7. **Attendus manuels contre calcul** : les tests confrontent `expected-fixture-1.json`, figé avant
   l'implémentation, au calcul. **Toute différence est expliquée** dans le rapport de test (erreur de calcul
   manuel ou subtilité de définition), et **jamais corrigée automatiquement** dans un sens ou dans l'autre
   sans revue.

## 7. Attendus manuels figés (révision 2)
- `expected-fixture-1.json` : la page `fixture-1-order`, dans les deux variantes. Elle est conforme aux
  définitions corrigées : surfaces de rectangles, baselines plates, largeur de la colonne 1 par statistique
  d'ordre `[42, 102]` → 42.
- `expected-micro.json` : cas aux seuils de l'audit, sur structures `pg` et fonctions du moteur :
  - `q` sur [], [7] et [0, 10] ;
  - statistique d'ordre [1, 2, 3, 100] → 3 ;
  - regroupement à 0,015 W, fusion à 0,06 W, poids exactement 4 % ;
  - aire stable et AABB variable sous rotation ;
  - baseline à points non uniformes ;
  - écart exactement égal à 4 × la médiane exclu ;
  - titre à 1,5 colonne exactement (non multi-colonnes) et juste au-dessus ;
  - en-tête d'annonce de structure heading, couvert par une AdvertRegion, qui donne `annonce_avec_titre` 0.

Les SHA-256 de ces fichiers et de cette spécification sont dans `SHA256SUMS`.
