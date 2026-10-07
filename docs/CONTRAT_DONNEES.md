# Contrat de données — Mille Feuilles

Version **0.2.0**, 7 octobre 2026. Ce contrat remplace la proposition 0.1.0.
Les schémas exécutables sont `schemas/{manifest,assets,page}.schema.json` ;
les invariants complémentaires sont dans `src/mille_feuilles/validation.py`.
Les décisions du cadrage sont résolues dans [DECISIONS.md](DECISIONS.md).

## 1. Périmètre

Mille Feuilles produit une image de page et sa vérité de composition : blocs,
articles, lignes, mots, ordre, provenance et transformations. Le profil pilote
est **`fr_press_19c_columns_4_6`**, presse française du XIXe siècle, 4 à 6
colonnes, 100 pages. La priorité est la segmentation et l'ordre de lecture.
Aucun modèle OCR n'est nécessaire. Un lot de démonstration en langue française
originale permet de vérifier le système ; il ne prouve pas le réalisme lexical
ou historique d'un corpus de presse.

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
vont dans `extensions`, avec clés préfixées par projet (`mille_feuilles:...`).
Les paramètres résolus et les métadonnées d'actifs sont des objets JSON ouverts.

## 3. Manifeste et actifs

| Champ de `manifest.json` | Contenu |
|---|---|
| `schema_version` | `"0.2.0"` |
| `dataset_id` | Identifiant stable du lot |
| `profile` | `"fr_press_19c_columns_4_6"` |
| `generator` | `{commit, dirty, environment_path, environment_sha256}` ; commit Git complet |
| `config` | `{path, sha256}` de la configuration résolue |
| `rng` | `{algorithm, version, seed}` ; seed entier entre 0 et 2^53−1 |
| `assets` | `{path, sha256}` du registre |
| `calibration` | `{protocol_path, protocol_sha256, source_partitions, files_read}` ; `files_read` vaut `{path, sha256}` |
| `pages` | Liste de `{id, path, sha256, source_group_ids}` |
| `artifacts` | Liste de `{path, sha256, role}`, incluant images, actifs, exports, planches QA et fichiers de reproduction |

`source_partitions` contient seulement `train` et/ou `dev`. Les fichiers
protocoles et inventaires sont embarqués ; aucun contenu de test n'est lu.
`source_group_ids` inclut les identifiants des documents source des textes
composés et permet de garder ensemble les dérivés lors d'un découpage aval.
Le manifeste ne fixe pas les partitions expérimentales d'Axel.

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

Le pilote utilise **un actif texte par document**, avec
`metadata.source_document_id` stable et règles de préparation documentées.
Une fonte documente sa famille, version, face et axes utilisés. L'environnement
fixe Python, rendu, shaping, rasterisation, dépendances et paramètres. Une graine
seule ne garantit pas une reproduction bit à bit.

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

Chaque `text_span` est `{asset_id, start, end, source_document_id}`. L'intervalle
semi-ouvert est en **points de code Unicode** dans l'actif UTF-8 original,
avant préparation. Il est non vide, dans les bornes de l'actif, et son document
correspond à `metadata.source_document_id`. Les actifs utilisés sont déclarés.
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
OCR. Le pilote n'accepte comme supervision OCR que le texte visible `readable` ;
il limite les dégradations et vérifie les pages et des échantillons de mots.
Les autres états restent représentables pour des expériences ultérieures mais
n'autorisent pas la supervision silencieuse d'un contenu masqué.

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

## 6. Texte, césure et ordre

Transcription diplomatique NFC : pas de NFKC, correction, modernisation ou
suppression d'accents. Conserver `ſ` et les ligatures Unicode du texte composé.
Une ligature typographique de shaping `fi` reste deux caractères si la source
était `fi`. Les espaces de composition sont U+0020 ; aucun espace de bord,
tabulation ou saut de ligne dans une ligne. Pas de texte invisible supervisé.
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

La QA des 100 pages est consignée avec les limites du profil. Des tests de
mutations doivent rejeter les violations (empreintes, dimensions, chemins,
références, texte, géométrie et exports), même lorsqu'un fichier altéré est
réempreinté. Une QA synthétique ne démontre aucun gain de modèle sur du réel.
Les seuils et tests gelés d'Axel ne sont jamais modifiés par Mille Feuilles.

## 9. Migration depuis 0.1.0

Aucun lot canonique 0.1.0 n'a été livré avant le moteur. Il n'existe donc pas de
migration de données implicite. Un import futur de 0.1.0 doit déclarer sa migration :
profil 4–6, séparation des blocs ordonnés/non ordonnés, document source des spans,
DPI initial/final et inventaire de calibration. Le validateur refuse 0.1.0 ; il
ne complète pas silencieusement les informations absentes.
