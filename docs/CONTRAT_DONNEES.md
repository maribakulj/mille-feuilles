# Contrat de données — Mille Feuilles

Version **0.3.0**, 7 octobre 2026. La lecture des lots **0.2.0** reste prise en
charge selon leur contrat historique ; leurs garanties ne deviennent pas
automatiquement celles de 0.3.0. La proposition 0.1.0 reste refusée.
Les schémas exécutables sont `schemas/{manifest,assets,page}.schema.json` ;
les invariants complémentaires sont dans `src/mille_feuilles/validation.py`.
Les décisions du cadrage sont résolues dans [DECISIONS.md](DECISIONS.md).

## 1. Périmètre

Mille Feuilles produit une image de page et sa vérité de composition : blocs,
articles, lignes, mots, ordre, provenance et transformations. Le profil pilote
est **`fr_press_19c_columns_4_6`**, presse française du XIXe siècle, 4 à 6
colonnes. Le pilote historique 0.2 comprend 100 pages ; ce nombre ne constitue
pas une preuve de livraison 0.3. La priorité est la segmentation et l'ordre de lecture.
Aucun modèle OCR n'est nécessaire. Un lot de démonstration en langue française
originale permet de vérifier le système ; il ne prouve pas le réalisme lexical
ou historique d'un corpus de presse.

Le lot 3 ajoute le profil distinct **`fr_press_19c_columns_4_6_measured`**, en
schéma **0.3.0** également. Il conserve la vérité de composition et mesure les
effets d'un profil de dégradation déclaré. Son acceptation passe 652 tests et
224 contrôles CLI, sur six pages de référence ; les preuves et les limites des
étiquettes heuristiques sont dans [VALIDATION](VALIDATION.md).

Le lot 4 en développement ajoute **`fr_press_19c_layout_v2`**, également en 0.3.0,
avec `template_press_v2`. Il combine une mise en page par zones et les mêmes
diagnostics mesurés ; les garanties des lots précédents ne valent pas à elles
seules acceptation de ce nouveau profil.

Le JSON canonique est la source des projections PAGE XML, ALTO et COCO.
Aucun import du logiciel Axel dans le générateur. Les adaptations de métriques,
les expériences et les tests réels gelés d'Axel restent dans son dépôt.
Le mandat d'autonomie de Marcel confie les conventions et la QA au coordinateur
et aux agents Mille Feuilles ; il ne conditionne pas le pilote à une validation
humaine de chaque page. Le contrôle visuel demeure obligatoire et consigné.

## 2. Fichiers et types

Un lot embarque `manifest.json`, `assets.json`, sa configuration résolue, son
environnement, les références légères de calibration, les actifs nécessaires,
`pages/<id>.json`, `images/<id>.png`, les exports et les planches de QA.
Le manifeste inventorie les fichiers avec SHA-256. Les corpus réels de calibration
ne sont pas copiés : leur inventaire historique est un justificatif, jamais une
instruction de lecture pour le validateur.

JSON UTF-8 strict : aucune clé dupliquée, NaN ou Infinity, aucun nombre non fini,
aucun horodatage variable dans les annotations. Les chemins de fichiers sont
relatifs à la racine, utilisent `/`, sans segment vide, `.` ou `..`, ni antislash,
ni chemin absolu. Une résolution de lien symbolique hors du lot est rejetée
avant lecture. Les URI de provenance ne sont pas des chemins à ouvrir.
Les empreintes SHA-256 sont 64 chiffres hexadécimaux minuscules, sur les octets.

Un identifiant suit `[A-Za-z_][A-Za-z0-9_.-]*`. L'identifiant de page est unique
dans le lot. Dans une page, les identifiants de page, articles, blocs, lignes et
mots sont uniques ensemble. Les identifiants de groupe de césure sont un espace
de noms séparé. Une référence doit pointer vers le bon type. Les dimensions sont
des entiers positifs ; les coordonnées sont finies.

Les objets structurés refusent les champs inconnus. Les extensions facultatives
vont dans `extensions`, avec clés préfixées par projet, notamment `mf:...`.
Les paramètres résolus et les métadonnées d'actifs sont des objets JSON ouverts.

## 3. Manifeste et actifs

| Champ de `manifest.json` | Contenu |
|---|---|
| `schema_version` | `"0.3.0"` ; `"0.2.0"` accepté en lecture historique |
| `dataset_id` | Identifiant stable du lot |
| `profile` | `"fr_press_19c_columns_4_6"`, `"fr_press_19c_columns_4_6_measured"` ou `"fr_press_19c_layout_v2"` ; les deux derniers exigent 0.3.0 |
| `generator` | `{commit, dirty, environment_path, environment_sha256}` ; commit Git complet |
| `config` | `{path, sha256}` de la configuration résolue |
| `rng` | `{algorithm, version, seed}` ; seed entier entre 0 et 2^53−1 |
| `assets` | `{path, sha256}` du registre |
| `calibration` | `{protocol_path, protocol_sha256, source_partitions, files_read}` ; `files_read` vaut `{path, sha256}` |
| `pages` | Liste de `{id, path, sha256, source_group_ids}` |
| `artifacts` | Liste de `{path, sha256, role}`, incluant images, actifs, exports, planches QA et fichiers de reproduction |

`calibration.source_partitions` contient seulement `train` et/ou `dev`. Il
désigne les sources de calibration, pas les partitions synthétiques décrites
ci-dessous. Les protocoles et inventaires sont embarqués ; leur présence ne
déclenche aucune lecture de contenu de test Axel.

En **0.3**, `pages[].source_group_ids` est exactement l'union des
`metadata.source_group_id` des actifs utilisés par les `text_spans` de la page.
Un actif simplement présent dans le registre ou dans `asset_ids` n'ajoute pas
de groupe. En **0.2**, ce champ conserve son sens historique : il doit inclure
les `source_document_id` des segments composés, et peut contenir des valeurs
supplémentaires. Le nom du champ ne suffit donc pas à interpréter sa sémantique
sans lire la version. Ces partitions ne fixent pas celles des expériences Axel.

`artifacts` exclut `manifest.json` et **`qa/report.json`** : aucun cycle
empreinte/rapport. La QA écrit ce rapport après la validation et contrôle
séparément son résultat ; un rapport modifié exige une nouvelle QA, ses octets ne
sont pas authentifiés par le manifeste. `dirty` est factuel et accepté pendant le
développement ; la livraison reproductible référence un commit propre.

`assets.json` vaut `{schema_version, assets: [...]}`. Chaque actif contient
`{id, kind, path, sha256, source_uri, rights, metadata}`. `kind` vaut `text`,
`font`, `texture`, `illustration` ou `template`. Les bytes nécessaires sont
embarqués et inventoriés. `rights` contient
`{status, license, evidence_uri, attribution, redistribution_allowed}`.
Le validateur de lot exige `status: "verified"` et
`redistribution_allowed: true`. Une déclaration n'est pas une expertise
juridique : les preuves et licences sont conservées avec les ressources.

L'import conserve **un actif texte par document**, avec
`metadata.source_document_id` stable et règles de préparation documentées.
Le catalogue 0.3 renseigne aussi `source_group_id`, `role` (`body`, `title`,
`advertisement`) et `language`. Plusieurs documents peuvent servir un même
rôle. Le registre 0.3 d'un lot généré renseigne explicitement les groupes ; à
l'entrée d'un catalogue historique 0.2, un groupe absent prend l'identité du
document. Cette compatibilité ne découvre pas les variantes non déclarées.
Une fonte documente sa famille, version, face et axes utilisés. L'environnement
fixe Python, rendu, shaping, rasterisation, dépendances et paramètres. Une graine
seule ne garantit pas une reproduction bit à bit.

### 3.1. Import et unités de composition

L'import local prend un manifeste JSONL explicite, conserve les sources UTF-8
et leurs preuves de droits, puis écrit un catalogue vérifié. Il refuse les
doublons d'identité documentaire ou d'empreinte de document selon les règles
de l'importeur ; les variantes d'une même origine doivent partager un groupe.
Le format détaillé et les exclusions sont décrits dans [ACTIFS.md](ACTIFS.md).

Les unités sélectionnables sont les paragraphes de corps et d'annonces, et les
lignes de titre non vides. Le compositeur tire uniformément parmi les unités
disponibles d'un rôle, tous documents sélectionnés réunis. Ce n'est pas un
tirage uniforme des documents : un document comportant davantage d'unités pèse
davantage. Ni l'import ni la multiplication des pages ne garantissent une
distribution historique représentative.

S'il existe, le rapport d'import est copié dans `provenance/import-report.json`,
inventorié et référencé par `manifest.extensions['mf:import_report']` avec
`{path, sha256}`. Il garde ses résultats et limites d'origine.
Le contrôle `import_receipt` confronte sa référence à l'inventaire et exige
une correspondance exacte entre `accepted[]` et les textes du catalogue source
global (identifiant, document, groupe, rôle, SHA-256). Il ne réévalue pas les
listes d'exclusion. Sans fichiers
d'exclusion fournis, la protection externe reste **`NOT EVALUATED`** ; une
partition interne cohérente ne prouve pas l'absence de recouvrement avec Axel
ou avec un corpus externe. Aucun corpus de test externe n'est ouvert pour
déduire cette protection.

### 3.2. Partition avant génération et reçu embarqué

Le plan `assets/partition.json` est calculé sur le bundle source complet.
Les documents d'un même groupe sont indivisibles ; les groupes partageant une
unité sélectionnable identique après NFC et réduction des espaces sont réunis
dans une composante, tous rôles confondus. Un titre ou une annonce partagée
peut donc relier deux ensembles de corps. La garantie concerne les groupes
déclarés et ces unités normalisées ; elle ne détecte pas tous les passages
partiels communs, les quasi-doublons ou les variantes non déclarées.

Les poids `ratios` sont finis et non négatifs, leur somme finie et positive ;
ils ne sont pas nécessairement stockés avec une somme égale à 1. Ils définissent
des cibles relatives de caractères. Une partition de poids nul reste vide ;
chacune de poids positif doit disposer des trois rôles. Les composantes restent
entières, donc les proportions réellement obtenues peuvent différer des cibles.
Une couverture impossible est refusée ; si la recherche atteint sa limite,
le diagnostic ne prétend pas avoir démontré l'impossibilité. Les trois textes
de démonstration, dans un même groupe, ne permettent pas trois partitions
non vides indépendantes.

Quand un plan existe, omettre `--partition` est une erreur : le générateur ne
revient pas silencieusement à l'ensemble du catalogue. Lors d'une sélection
initiale, `load_partition` recalcule le graphe et le plan depuis les fichiers
du bundle complet vérifié avant le rendu.

Un lot sélectionné embarque seulement les textes de sa partition, les actifs
de rendu et leurs preuves. Son `assets/catalog.json` est filtré. Deux fichiers
supplémentaires conservent le plan et le catalogue original :
`provenance/partition.json` et `provenance/source-catalog.json`. Ce dernier est
une copie des **métadonnées de toutes les partitions** : identités documentaires,
groupes, chemins, `source_uri`, SHA-256 et droits peuvent donc révéler les
références des sources dev/test. Il ne contient pas leurs textes.

Le même reçu est présent dans `manifest.extensions['mf:partition']` et dans
`config.json['partition']` :

| Champ du reçu | Valeur |
|---|---|
| `version` | `"1"` |
| `name` | Nom de la partition sélectionnée |
| `path`, `sha256` | `provenance/partition.json` et son empreinte |
| `source_catalog_path`, `source_catalog_sha256` | `provenance/source-catalog.json` et son empreinte |

`config.render.partition` et `page.provenance.parameters.partition` portent
ce même nom. Sans sélection, le paramètre vaut `null` et le reçu est absent.
Le lot n'a alors aucune garantie d'isolation de partitions.

`validate_partition_receipt(root, manifest, registry)` ne lit que les
métadonnées : JSON strict, chemins, empreintes, inventaire, identités sélectionnées,
groupes/documents/SHA confinés à une partition, couverture de tous les textes,
rôles, composantes et sommes de caractères déclarées. Le registre et le
catalogue filtré doivent contenir exactement les identifiants texte du plan
pour cette partition, avec les mêmes chemins, empreintes, documents, groupes
et rôles que le catalogue original. Le fallback groupe=document concerne le
catalogue source 0.2, pas un groupe manquant dans un registre 0.3.

La validation complète compare en plus les comptes de chaque composante
sélectionnée et `characters[name]` aux longueurs Unicode réelles des textes
embarqués. Pour les composantes exclues, elle ne vérifie que la cohérence des
métadonnées. Elle ne recalcule pas leur contenu ni le graphe global : cela
nécessite toujours le bundle complet d'origine.

Un lot filtré peut servir à une nouvelle génération en indiquant la **même**
`--partition`. La prévalidation contrôle son reçu, puis ses actifs sélectionnés ;
elle n'appelle pas `load_partition` sur le catalogue tronqué et ne valide pas
toutes les anciennes pages ou leurs exports. Un changement de partition exige
de revenir au bundle complet.

## 4. Page canonique

| Champ | Contenu |
|---|---|
| `schema_version`, `page_id`, `profile` | Version, identifiant et profil du manifeste |
| `image` | `{path, sha256, width, height, color_mode, dpi}` ; PNG `L` ou `RGB`, `dpi > 0` |
| `language` | `"fr"` |
| `provenance` | `{seed, template_id, asset_ids, text_spans, parameters}` |
| `transforms` | Liste ordonnée des transformations |
| `articles` | Liste de `{id, block_ids}` |
| `blocks` | Liste de blocs |
| `lines` | Liste de lignes |
| `words` | Liste de mots |
| `reading_order` | `{block_ids, unordered_block_ids, line_ids}` |

`parameters` inclut `columns` (4 à 6) et `render_dpi > 0`, résolution physique
initiale distincte de `image.dpi`, résolution finale. Les autres valeurs résolues
(corps, marges, interlignage, dégradations...) y sont conservées. La métadonnée DPI
PNG, lorsqu'elle existe, doit correspondre à la résolution finale à 0,1 dpi près.
`template_id` référence un actif `template` présent dans `asset_ids`.

En **0.3**, chaque `text_span` est
`{asset_id, start, end, source_document_id, article_id, block_ids}`. L'intervalle
semi-ouvert est en **points de code Unicode** dans l'actif UTF-8 original,
avant préparation. Il est non vide, dans les bornes de l'actif, et son document
correspond à `metadata.source_document_id`. Les actifs utilisés sont déclarés.
`article_id` doit posséder les blocs indiqués ; `block_ids` est non vide,
sans doublons, dans l'ordre de cet article. Un titre peut désigner un bloc et
un corps plusieurs blocs, notamment à travers des colonnes. Le texte exact
de ces blocs, après reconstruction des seules césures annotées, doit égaler
le segment source après NFC et réduction des espaces. Une occurrence correcte
dans un autre article ne compense pas une mutation du texte lié. Les tirets
lexicaux et la ponctuation restent inchangés. L'ordre des spans ne définit pas
l'ordre de lecture.

Chaque bloc textuel est couvert exactement une fois. Une césure ne traverse
pas deux propriétaires de provenance. La seule exemption est le bandeau
explicitement déclaré par
`provenance.extensions['mf:template_article_ids']` : liste sans doublon,
ordonnée dans la lecture, sans span concurrent. La concaténation de ces articles
doit égaler exactement la liste `metadata.literal_text` du template référencé,
après la même normalisation. Un article quelconque ne peut donc pas être
exempté sous couvert de gabarit.

En **0.2**, les spans restent `{asset_id, start, end, source_document_id}`.
Le contrôle historique demande seulement une occurrence dans un article ou
un bloc sans article ; il ne prouve ni attribution unique, ni multiplicité,
ni couverture du gabarit. Cette faiblesse n'est pas présentée comme résolue
pour les anciens fichiers sans nouvelle annotation.
Les titres et textes composés ne deviennent pas une source historique par le
simple fait de leur rendu dans une maquette ancienne.

Un bloc est `{id, category, polygon, article_id, line_ids}`. Catégories :
`titre`, `texte`, `legende`, `annonce`, `tableau`, `illustration`, `separateur`,
`autre`. Vocabulaire aligné sur Axel au commit
`79c5fa4050380ae80897438d365b5042e4d709ec`, sans dépendance de code.
Les appartenances article/bloc sont réciproques et uniques. Un filet est
`separateur`, sans article ni ligne. `illustration` et `separateur` sont
non textuels ; les autres catégories possèdent au moins une ligne.
Chaque annonce appartient à un article d'annonce propre, éventuellement plusieurs
blocs. Le bandeau (journal fictif, date, adresse) forme un article dédié, dont
les lignes sont des blocs `titre` ou `texte` selon leur fonction.

Une ligne est `{id, block_id, polygon, baseline, text, word_ids, legibility}`.
Elle appartient à un seul bloc. Chaque ligne physique d'un titre est une ligne
distincte. `baseline` est la **ligne de base typographique** du rendu, une
polyligne simple, non dégénérée, d'au moins deux points, de gauche à droite.
Le pilote compose des lignes horizontales puis applique, si demandé, la rotation
commune à l'image et aux annotations.

Un mot est `{id, line_id, polygon, text, char_span, legibility, hyphenation}`.
Il appartient à une seule ligne. `char_span: [start, end]` est non vide, en
points de code de `line.text`, et désigne exactement `word.text`. Les intervalles
sont ordonnés et disjoints ; les caractères non couverts sont seulement U+0020.
La ponctuation attachée reste dans le mot ; une ponctuation isolée est un mot.
Un mot ne contient aucun espace. Les références parent/enfant sont réciproques.

`legibility` vaut `readable`, `uncertain` ou `illegible`. Une ligne porte le pire
état de ses mots. Ce champ est une décision de génération/QA, pas une confiance
OCR. Le profil historique `fr_press_19c_columns_4_6` exige que tous les mots
soient `readable` et conserve ses contrôles de pages et d'échantillons.
Le profil mesuré autorise les trois états, selon la règle `heuristic-v1`
décrite ci-dessous. La présence du texte de composition d'un mot masqué dans
le canonique n'autorise pas son utilisation silencieuse comme supervision OCR.

### 4.1. Profil mesuré et diagnostics

La CLI sélectionne un profil avec **`--degradation-profile identity`**,
**`--degradation-profile controlled-v1`** ou le chemin d'un fichier JSON.
Le facteur `oversampling`, **1 ou 2**, appartient au même JSON ; aucun second
drapeau CLI ne le sélectionne. Un profil contient
`{format, version, name, description, calibrated, oversampling, families}`,
avec `format: "mille-feuilles-degradation-profile"`, `version: "1"` et
`calibrated: false`. Le schéma exécutable est
`schemas/degradation-profile.schema.json` ; les familles, distributions et
bornes figurent dans [DEGRADATIONS.md](DEGRADATIONS.md).

`identity` conserve la rotation : son identité concerne seulement la
photométrie. Un profil mesuré remplace les anciens réglages photométriques pour
la page. Sans ce profil, les modes `clean`, `aged`, `faint` et `mixed` conservent
leurs PNG et annotations canoniques à l'identique dans l'environnement
verrouillé, sans nouvelle clé dans leurs pages. Les empreintes de code et le
commit du manifeste continuent de décrire la version réellement exécutée.

Le profil complet est enregistré dans `config.render.degradation_profile` et
copié dans `provenance/degradation-profile.json`. Le manifeste le référence par
`extensions['mf:degradation_profile'] = {path, sha256}` et l'inventorie.
Le validateur exige l'égalité du profil copié et du profil de configuration.
Les paramètres tirés pour chaque page sont dans
`page.provenance.parameters.degradation_profile` : nom, `profile_sha256`, graine
propre à la dégradation et valeurs résolues par famille. `profile_sha256`
empreinte la sérialisation JSON canonique du profil, triée et compacte ; la
référence du manifeste empreinte les **octets du fichier** copié. Ces deux
empreintes ont donc des fonctions distinctes.

Les flux aléatoires de dégradation sont séparés de la composition. À sources,
paramètres de composition, graine et facteur de suréchantillonnage identiques,
deux profils mesurés produisent les mêmes sources sélectionnées, positions,
retours de ligne, géométries et masque idéal. La garantie de géométrie et de
masque identiques vaut **entre profils mesurés de même facteur** ; les métriques
des glyphes dessinés à taille double peuvent ajuster leurs enveloppes. Elle ne
constitue pas une garantie d'identité avec une page du profil historique.

La couverture idéale est dessinée avant toute altération photométrique :
texte à 1, fond à 0, filets à 200/255. Elle reçoit la rotation et, au facteur 2,
la réduction par moyenne des blocs de couverture **grise**. Le masque est
ensuite obtenu par le seuil `couverture >= 0.5` ; un masque binaire n'est pas
réduit. Il inclut les filets et est conservé même lorsque l'image perd de
l'encre. Les effets photométriques s'appliquent après cette réduction ; leurs
unités en pixels correspondent à l'image finale.

Chaque page mesurée possède :

| Fichier ou champ | Contenu |
|---|---|
| `qa/masks/<id>.png` | PNG de mode `1`, dimensions finales ; blanc = encre idéale |
| `qa/diagnostics/<id>.json` | Résultat exact de `diagnostics.document(image, mask, page, ...)` |
| `page.extensions['mf:diagnostics']` | `{version: "1", path, sha256, mask_path, mask_sha256}` |
| `diagnostics.inputs` | Références `image` et `mask`, chacune `{path, sha256}` |
| `provenance.parameters.legibility_method` | `"heuristic-v1"` |
| `provenance.parameters.oversampling` | 1 ou 2 |
| `provenance.parameters.raster_width`, `raster_height` | Dimensions finales multipliées par le facteur |

Le masque, les diagnostics et le profil copié figurent dans l'inventaire des
artefacts. `validate_dataset` contrôle leurs chemins, empreintes et références,
rééchantillonne les paramètres depuis le profil et la graine du lot, puis
recalcule le document de diagnostics. Les mesures arrondies à six décimales,
seuils versionnés, étiquettes des mots et pire état des lignes doivent
correspondre. Une simple réempreinte d'une mesure ou étiquette altérée ne suffit
pas à la rendre valide. Ces étiquettes sont appliquées avant les exports.

**Portée de `heuristic-v1`.** Les seuils utilisent le contraste, la quantité
de pixels d'encre idéale et leur rétention. Ils ne certifient ni lecture humaine
ni supervision OCR : une lettre amputée peut laisser le mot `readable`.
Le profil mesuré conserve explicitement les mots `uncertain` et `illegible` ;
leur texte reste la vérité de composition, pas une transcription garantie
lisible de l'image finale. Les seuils et contre-exemples sont documentés dans
[DEGRADATIONS.md](DEGRADATIONS.md).

**Portée de la vérification du masque.** Son occupation est contrôlée dans
l'union rasterisée des blocs, filets inclus, avec une marge de 3 pixels.
Cette vérification n'établit pas que chaque pixel correspond au glyphe source.
Le validateur ne reconstruit pas les glyphes pour authentifier le masque idéal :
un masque falsifié, puis réempreinté et accompagné de diagnostics cohérents,
peut rester conforme à l'occupation des blocs. Les empreintes, le recalcul des
mesures et ce contrôle spatial prouvent une cohérence dans leur périmètre ;
la reproduction et la revue visuelle apportent des vérifications complémentaires.

### 4.2. Mise en page par zones

`fr_press_19c_layout_v2` exige `config.render.layout_profile` de même valeur,
un profil de dégradation explicite et l'actif `template_press_v2`. Il conserve
les diagnostics du §4.1. Les options de mise en page du gabarit sont celles du
preset version 1, déclarées `calibrated: false`. `--columns` contraint seulement
la zone principale ; la validation confronte cette contrainte au plan.

Le plan dans `provenance.parameters.layout` est strict et exprimé en coordonnées
de composition, **avant rotation**, à la résolution finale. Il contient les
dimensions, marges, gouttière, une zone `main` puis éventuellement une zone
`rez_de_chaussee`, leurs rectangles, colonnes et filets de séparation. Les deux
zones ont des nombres de colonnes distincts. Les polygones des blocs, lignes et
mots restent dans le repère final et sont ramenés au plan par l'inverse affine
pour les contrôles de mise en page.

Un titre large conserve son enveloppe réelle, avec une réservation séparée
`headline_reserved`. Son article possède un bloc de corps par colonne couverte,
au moins deux lignes par bloc et un écart de compte de lignes d'au plus un. La
bande `headline_body_band` réserve tout ce corps, puis un espacement de fin
d'article ; les articles ordinaires commencent sous cette bande dans chacune
des colonnes couvertes. Les colonnes restantes commencent au haut de la zone.
Le segment source est conservé entier, y compris les césures entre colonnes.

Les paramètres `layout_body_ratio` et `layout_typography` décrivent le corps
normal commun aux zones, calculé depuis la largeur de colonne de `main`, et le
petit corps borné à 10 px. Chaque article hors bandeau porte
`extensions['mf:layout']` : zone, corps effectif, demande de petit corps,
réduction effective, titre large éventuel et cadre éventuel. Une annonce
encadrée reste dans une colonne ; quatre filets hors article forment son cadre
avec le padding déclaré. L'ordre est bandeau, articles de `main`, puis articles
du rez-de-chaussée ; tous les filets restent hors ordre textuel.

Les contrôles vérifient les rectangles disponibles, le non-chevauchement des
blocs textuels, les bandes, l'ordre et les quatre côtés des cadres. L'intersection
filet/texte est calculée sur les polygones exacts avec une tolérance d'aire de
0,5 px², distincte de la tolérance linéaire de 0,5 px. La fidélité aux glyphes
reste du ressort des contrôles de rendu et de reproduction du §4.1.

Les rejets précédant un succès sont séparés des 32 essais terminaux qui ferment
une zone. Un texte trop long ou un titre impossible peut provoquer un refus
contrôlé ; le moteur ne supprime pas silencieusement une structure tirée pour
faire passer la page. Les [règles détaillées](MISE_EN_PAGE.md) précisent le
filtrage des colonnes, les deux réservations et les limites non calibrées.

## 5. Géométrie

Les coordonnées sont celles de l'**image finale** : origine haut-gauche, x à
droite, y en bas, pixels, bords dans `[0,width] × [0,height]`. Un polygone simple
possède au moins trois sommets distincts, sans premier sommet répété à la fin.
Il a une aire positive et un parcours horaire à l'écran :
`sum(x[i]*y[i+1] - x[i+1]*y[i]) > 0` dans ce repère.

Les polygones décrivent les enveloppes exactes de composition, ascendants et
descendants inclus. Ce ne sont ni des masques d'encre ni des polygones OCR.
Mot inclus dans ligne, ligne dans bloc, ligne de base dans ligne, avec tolérance
0,5 pixel. Les blocs peuvent se chevaucher. Aucune inflation « façon NewsEye »
dans le canonique ; une adaptation aval doit la déclarer et rester séparée.

Chaque transformation vaut `{kind, parameters, geometry}`. `geometry` est
`"identity"` pour une opération photométrique ou
`{matrix: [[a,b,c],[d,e,f],[0,0,1]]}` pour une affine inversible, vecteurs colonne
de l'étape précédente vers la suivante. Les polygones et lignes de base subissent
la même affine que l'image. Les paramètres et graines locales sont explicites.
Pas de rognage textuel, courbure ou déplacement non affine dans ce pilote.
La transparence et les versos sont différés ; leur future provenance devra
identifier le contenu arrière et les sources partagées.

Dans le profil mesuré, le facteur 2 est décrit par
`mf:oversampling` (matrice d'échelle 2), la rotation dans le repère raster
double, puis `mf:downsample` (matrice d'échelle 1/2, `resampling: "box-mean"`).
Le produit de ces matrices ramène les coordonnées dans l'image finale ; les
métadonnées de taille de fonte restent en pixels finaux de composition.
Les transformations `mf:degrade:<famille>` viennent ensuite, toutes de
géométrie identité. Les enveloppes décrivent la composition idéale, même
quand l'image est floutée ou une partie de son encre effacée.

## 6. Texte, césure et ordre

Transcription diplomatique NFC : pas de NFKC, correction, modernisation ou
suppression d'accents. Conserver `ſ` et les ligatures Unicode du texte composé.
Une ligature typographique de shaping `fi` reste deux caractères si la source
était `fi`. Les espaces de composition sont U+0020 ; aucun espace de bord,
tabulation ou saut de ligne dans une ligne. Un contenu devenu invisible dans
un profil mesuré reste explicitement étiqueté ; sa présence dans le canonique
ne suffit pas à autoriser son emploi comme supervision.
Une fonte doit couvrir chaque caractère rendu ; aucun remplacement silencieux.
Les lettrines et symboles de texte substitués par une illustration sont exclus
du pilote jusqu'à définition d'une annotation mixte explicite.

`hyphenation` vaut `null` ou `{group_id, part, reconstructed_text}`, `part` valant
`start` ou `end`. Un groupe contient exactement deux mots, dernier mot de la
première ligne et premier de la suivante, **consécutives dans l'ordre de lecture
du même article**, y compris entre deux blocs ou colonnes. Le premier porte le
trait visible `-` ; `reconstructed_text` est le premier fragment sans son dernier
trait suivi du second. Les tirets lexicaux ne créent pas de groupe.
La conversion `-` vers `¬` pour une métrique NewsEye appartient à l'adaptateur.

`reading_order.block_ids` contient **tous et seulement les blocs textuels**,
une fois chacun. `unordered_block_ids` contient exactement les non textuels.
`line_ids` est la concaténation des `line_ids` des blocs ordonnés, chaque ligne
une seule fois. Aucun tri géométrique implicite. L'ordre est **article par
article** ; les blocs d'un article sont contigus et suivent `article.block_ids`.
Un article peut continuer en haut de la colonne suivante. La transcription de
page joint les textes de lignes par `\n`, sans saut final.

Les tableaux simples futurs seront sans cellules fusionnées, lus ligne par
ligne de gauche à droite puis de haut en bas. Les tableaux ambigus sont exclus.
Le pilote initial peut omettre les tableaux et les illustrations : son rapport
doit rendre ces lacunes de distribution visibles ; aucune catégorie n'est
fabriquée pour satisfaire un quota.

## 7. Exports

Le canonique accompagne chaque projection. Les XSD PAGE 2019-07-15 et ALTO 4.4
sont épinglés dans `schemas/xml/`, avec leurs dépendances et empreintes. Les
exports XML doivent passer la validation XSD locale et une relecture sémantique.

| Cible | Engagement |
|---|---|
| PAGE XML | Régions, lignes, mots, polygones, baselines, texte, ordre ; article et identifiants canoniques par mapping documenté |
| ALTO | Blocs, lignes, mots, rectangles englobants, texte et ordre sérialisé ; articles via projection et mapping documentés |
| COCO instances | Blocs : segmentation, bbox `[xmin,ymin,width,height]`, aire polygonale, `iscrowd=0` ; pas de promesse d'ordre ou d'articles natifs |
| Axel | Adaptateur séparé : dimensions finales, catégories, ordre, articles, vérité synthétique `score=1.0` |

COCO utilise les catégories 1–8 dans l'ordre de la section 4. Les identifiants
numériques ont une table vers le canonique. L'aire est celle du polygone, pas de
la bbox. Pour les coordonnées entières, arrondi au plus proche, demi vers +infini,
borne au cadre ; bbox arrondie vers l'extérieur. Un polygone devenu dégénéré est
rejeté. La tolérance d'export est 1 pixel. Les pertes de représentation sont
explicites dans le rapport/mapping ; pas de perte silencieuse de texte ou ordre.

Le profil canonique `autre` reste une catégorie indépendante. Son éventuelle
conversion en `texte` pour l'OLR d'Axel, et l'entraînement séparé des filets,
sont des conventions de l'adaptateur aval, jamais du COCO canonique.

## 8. Validation et livraison

`validate_page(page)` renvoie une liste d'erreurs. `validate_dataset(root,
verify_exports=True)` renvoie `{status, errors, checks}`, chaque contrôle ayant
`{name, status, detail}`. Désactiver explicitement les exports produit un contrôle
`not_run` et ne constitue pas un audit complet de livraison. Un contrôle requis
`fail` ou `not_run` empêche l'acceptation du pilote.

Conditions du pilote : JSON stricts et schémas compatibles ; intégrité et chemins
confinés ; dimensions/modes d'images ; références, spans Unicode, ordre et césures ;
géométries et baselines ; licences et provenance ; couverture des caractères ;
exports XSD et relecture ; planches contours/identifiants/baselines/ordre ; contrôle
visuel par page et échantillons ; reproduction bit à bit des images et annotations
dans le même environnement verrouillé, indépendante du parallélisme.

La QA des 100 pages du pilote historique 0.2 est consignée avec les limites du profil. Des tests de
mutations doivent rejeter les violations (empreintes, dimensions, chemins,
références, texte, géométrie et exports), même lorsqu'un fichier altéré est
réempreinté. Une QA synthétique ne démontre aucun gain de modèle sur du réel.
Les seuils et tests gelés d'Axel ne sont jamais modifiés par Mille Feuilles.

## 9. Compatibilité et migration

Le validateur lit 0.2.0 et 0.3.0, avec version de page égale à celle du manifeste.
Il ne complète pas les liens de provenance manquants d'un lot historique et
ne lui ajoute pas une partition déduite après coup. Les preuves du pilote
0.2, dont les 100 pages et la campagne complémentaire de 227 tests, restent
historiques. L'acceptation du lot 2 en 0.3, avec 483 tests et trois pages CLI,
est également distincte de la campagne mesurée du lot 3 encore en cours.
L'état d'acceptation figure dans [VALIDATION.md](VALIDATION.md).

Reproduire les octets du pilote 0.2 exige son commit de production
`0d1e2b701e9f6ba4d571a5f4894bd40071792225` et son environnement verrouillé.
La compatibilité de lecture avec le moteur courant ne promet pas une
régénération identique par le moteur 0.3.

Aucun lot canonique 0.1.0 n'a été livré avant le moteur. Il n'existe donc pas de
migration de données implicite. Un import futur de 0.1.0 doit déclarer sa migration :
profil 4–6, séparation des blocs ordonnés/non ordonnés, document source des spans,
DPI initial/final et inventaire de calibration. Le validateur refuse 0.1.0 ; il
ne complète pas silencieusement les informations absentes.
