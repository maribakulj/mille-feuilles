# Profil d'export `page-newseye-v1` — spécification normative (Claude, préparation sans code), révision 3

Statut : fixtures FIGÉES (révision 3 ; SPEC précisée en 3.1, index stricts) pour l'étape « lecteur d'abord » du lot 5. Arbitrages pris :
- PAGE 2019 déjà épinglé ;
- export à la demande ;
- éléments `Word` conservés ;
- contrôle avec le lecteur réel d'Axel laissé à sa coordination ;
- `paragraph` pour le texte des annonces ;
- catégories canoniques pour le bandeau.

La révision 2 intègre les remarques de Codex et de son agent :
- annonce au milieu de l'ordre ;
- ordre canonique différent de l'ordre du document et des identifiants ;
- refus documenté du bloc libre ;
- définition exacte du recouvrement ;
- mutations détectées par le **lecteur indépendant**, et pas seulement par l'égalité au XML attendu ;
- fixture Unicode, césure et géométrie.

## 0. Fixtures (preuve indépendante, écrites à la main, aucune sortie de producteur)
| Fichier | Rôle |
|---|---|
| `fixture-1-order.json` | Page 0.3.0 (`validate_page` = []). Ordre de lecture `b0000, b0004, b0003, b0001, b0002`, différent de l'ordre des identifiants ; l'**annonce `b0003` est au rang 2 sur 5**, entre deux régions ordinaires ; un filet hors ordre. |
| `fixture-1-order.expected.xml` | Sortie attendue, validée par le XSD PAGE 2019. |
| `fixture-1-order.reader-variant.xml` | **Réservée au lecteur.** Même contenu, mais régions en ordre de document inversé et deux `TextLine` permutées ; `RegionRefIndexed` et `readingOrder {index}` inchangés ; validée par le XSD. Ce n'est pas une sortie de producteur. Elle est dérivée du XML attendu par la transformation documentée de `make_reader_variant.py`. |
| `fixture-1-order.expected-reading.json` | Lecture attendue, identique pour les deux XML ci-dessus. |
| `fixture-2-unicode-hyphen-geometry.json` | Page 0.3.0 (`validate_page` = []) : NFC (Œ, é, ’, « », —), `&` à échapper, groupe de césure `disso-`/`lution`, polygones fractionnaires dont un quadrilatère non rectangulaire, baselines fractionnaires. |
| `fixture-2-unicode-hyphen-geometry.expected.xml` | Sortie attendue (XSD valide). Les coordonnées y sont arrondies **à la main** par `floor(v + 0,5)`. |
| `fixture-2-unicode-hyphen-geometry.expected-reading.json` | Lecture attendue ; tiret visible conservé, sans reconstruction. |
| `fixture-3-free-block.json` | Page **0.2.0** valide (`validate_page` = []) dont le bloc textuel `b0004` n'appartient à aucun article. |
| `fixture-3-free-block.expected-error.json` | Refus contrôlé attendu (§ 3.3). |
| `fixture-4-advert-overlap.json` | Page 0.3.0 valide dont le bloc d'annonce `b0003` (y 60–95) chevauche le bloc ordinaire `b0004` (y 50–65). |
| `fixture-4-advert-overlap.expected-error.json` | Refus contrôlé `advert_overlap` attendu (§ 3.3). |
| `fixture-1-order.expected-geometry.json`, `fixture-2-…expected-geometry.json` | **Tous** les points `Coords` (régions, AdvertRegion, filet, lignes, mots) et `Baseline`, ainsi que le texte de chaque `Word`, saisis à la main. La fixture 2 contient une baseline à **trois points** (`10,82 81,82 150,82`). |
| `source-fixture-1.txt`, `source-fixture-2.txt` | Sources textuelles **originales**, écrites à la main pour ces fixtures. Les spans des pages y pointent exactement : `validate_text_provenance` = [] pour les quatre pages. |

`make_canonical.py` et `make_expected_geometry.py` ne font que sérialiser des valeurs écrites à la main.
Les pages ont été validées par `validate_page` et `validate_text_provenance` à l'arbre du commit
`bdb4366` (code `69f0e50`).

**Portée des fixtures.** Elles prouvent la projection et la lecture sur des cas construits : textes,
Unicode, césure, arrondis, ordre et annonces. Elles ne prouvent rien sur les pages réelles : une égalité
au XML attendu ne garantit pas les mots ni les géométries d'autres pages. D'où la preuve 4 du § 7, qui
compare la lecture au canonique sur des pages réelles.

## 1. Entrée et sortie
- Entrée : une page canonique **validée** (0.2.0 ou 0.3.0), lue dans un lot existant immuable.
- Sortie : un document PAGE 2019 par page, dans une destination **neuve**.
- La projection est une fonction pure : à page égale, octets égaux.

## 2. Structure du document (ordre imposé)
1. `PcGts`, avec `pcGtsId="p_<page_id>"` et `xsi:schemaLocation` comme l'export générique.
2. `Metadata` :
   - `Creator` = `Mille Feuilles` ;
   - `Created` et `LastChange` = `1970-01-01T00:00:00Z` ;
   - `Comments` = `Synthetic composition. Projection page-newseye-v1; fixed dates are reproducibility sentinels.` ;
   - pas de `UserDefined`, pas de JSON.
3. `Page` : `imageFilename`, `imageWidth`, `imageHeight`, `primaryLanguage="French"` (seul `fr` est
   accepté).
4. `ReadingOrder/OrderedGroup id="mf_newseye_order"` : un `RegionRefIndexed index=i regionRef="r_<bloc>"`
   par identifiant de `reading_order.block_ids`, dans cet ordre. **Aucune référence à une
   `AdvertRegion`**, à une `SeparatorRegion` ni à une `GraphicRegion`. Le texte des annonces est, lui,
   référencé par sa `TextRegion`.
5. Régions, dans cet ordre :
   - pour chaque bloc de `reading_order.block_ids` : sa `TextRegion`, immédiatement suivie de son
     `AdvertRegion` si la catégorie est `annonce` ;
   - puis les blocs de `reading_order.unordered_block_ids`, dans cet ordre (`SeparatorRegion
     id="s_<bloc>"` ou `GraphicRegion id="g_<bloc>"`).

## 3. Correspondances
### 3.1 Régions, lignes et mots
| Canonique | Élément | Attributs |
|---|---|---|
| `titre` | `TextRegion` | `id="r_<bloc>"`, `type="heading"`, `custom="readingOrder {index:n;} structure {type:heading;}"` |
| `texte` | `TextRegion` | `type="paragraph"`, `custom="readingOrder {index:n;} structure {type:paragraph;}"` |
| `legende` | `TextRegion` | `type="caption"`, `custom="… structure {type:caption;}"` |
| `annonce` | `TextRegion` comme `texte`, **puis** `AdvertRegion id="a_<bloc>"` sœur | `Coords` de l'AdvertRegion **identiques** à ceux de la TextRegion ; aucun enfant ni attribut de plus |
| `autre` | `TextRegion` comme `texte` | perte déclarée |
| `tableau` | — | refus contrôlé `table_block` (non produit par les profils actuels) |
| ligne | `TextLine id="l_<ligne>"` | `custom="readingOrder {index:j;} structure {id:<article_id>; type:article;}"`, avec j le rang dans le bloc ; enfants `Coords`, `Baseline`, `Word`*, `TextEquiv` |
| mot | `Word id="w_<mot>"` | `Coords`, `TextEquiv/Unicode` = `word.text` (tiret de césure compris) |
| texte de région | `TextEquiv/Unicode` | lignes jointes par `\n`, sans saut final |

n est le rang dans `reading_order.block_ids`.

### 3.2 Textes
- Les textes sont recopiés **à l'identique**, en NFC, comme dans le canonique.
- L'échappement XML est celui de la sérialisation standard : `&` → `&amp;`, `<` → `&lt;`.
- Aucune normalisation, aucun remplacement typographique, aucune reconstruction de césure.

### 3.3 Refus contrôlés (classe `NewsEyeExportError`, sous-classe de `ValueError`)
Ce sont des décisions **du profil**, qui n'écrit alors rien dans la destination :
- `free_text_block` : un bloc textuel sans article. **Le profil le refuse.** Le canonique 0.3.0 ne produit
  pas ce cas (ses spans lient chaque bloc textuel non gabarit à un article), mais **le canonique 0.2.0
  l'admet**. Ce n'est donc pas le schéma qui refuse : c'est ce profil, faute de pouvoir exprimer l'article
  de la ligne. Fixture 3.
- `table_block` : catégorie `tableau`.
- `language` : langue autre que `fr`.
- `custom_value` : un identifiant hors `[A-Za-z0-9_.-]+`. Aucun échappement n'est tenté.
- `geometry` : polygone dégénéré ou auto-intersecté après arrondi (même règle que l'export générique).
- `advert_overlap` : après arrondi, une `AdvertRegion` a une intersection d'aire **strictement positive**
  avec une `TextRegion` autre que celle de son annonce. Règle prudente du profil, indépendante du seuil de
  `cover` : la géométrie n'est ni réduite ni déplacée. Fixture 4, où `cover(r_p_b0004)` vaudrait 0,283.

## 4. Grammaire `custom` et lecture conforme
**Grammaire.**
- Groupes `nom {clé:valeur;}` séparés par une espace ; paires internes séparées par une espace ; pas
  d'espace avant `}`.
- Ordre des groupes : `readingOrder`, puis `structure`. Ordre des paires sur une ligne : `id`, puis
  `type`.
- `index` est un entier décimal ; les identifiants sont dans `[A-Za-z0-9_.-]+` ; les types sont pris
  dans {`heading`, `paragraph`, `caption`, `article`}.

**Lecture conforme** (les lectures attendues appliquent ces règles à la main) :
1. Les `TextRegion` d'intérêt sont celles de premier niveau. Leurs lignes sont les `TextLine` enfants
   directs, triées par `readingOrder {index}`. **Profil strict** : chaque ligne porte un index. Les index
   d'une région doivent former exactement `0..k−1`. Un index manquant, dupliqué ou hors de cette suite est
   une **erreur de lecture contrôlée**. Aucun départage par l'ordre du document.
2. Ordre : les `RegionRefIndexed`, triés par `index`, visant des `TextRegion` connues. **Profil strict** :
   - les `index` des `RegionRefIndexed` forment exactement `0..n−1`, sans manquant ni doublon ;
   - une même `TextRegion` n'est référencée qu'une fois ;
   - l'index `readingOrder {index}` porté par chaque TextRegion référencée **égale** celui de sa
     référence.

   Tout manquement (index manquant, dupliqué, contradictoire, ou référence vers un élément qui n'est pas
   une TextRegion) est une erreur de lecture contrôlée, sans départage implicite. Les `TextRegion` non
   référencées sont rapportées dans `omitted_text_regions`, et le validateur du profil **refuse** une
   liste non vide.
3. **Recouvrement d'annonce**, défini exactement : pour une `TextRegion` T,
   `cover(T) = max sur les AdvertRegion A de aire(T ∩ A) / aire(T)`.
   - Polygones pris aux coordonnées entières du XML, intersection polygonale générale (par exemple
     Shapely `intersection`), aire euclidienne.
   - Un polygone invalide ou d'aire nulle est une erreur de lecture.
   - `cover(T) = 0` s'il n'y a aucune AdvertRegion.
   - Seuil **inclusif** : `cover(T) ≥ 0,5`.
4. Type :
   - `annonce` si `cover ≥ 0,5` ;
   - sinon `titre` si `structure {type:heading}` ;
   - sinon `legende` si `caption` ;
   - sinon `texte`.
5. Article d'une ligne : la valeur `id` du groupe `structure` de type `article`. Une ligne sans article
   est rapportée comme erreur de lecture.

Le profil vise **cette** lecture, datée des constats du 7 octobre 2026 (C1). Il ne revendique ni la
compatibilité avec tout lecteur NewsEye, ni avec Transkribus.

## 5. Coordonnées
- Chaque coordonnée devient `floor(v + 0,5)`, bornée à `[0, largeur]` ou `[0, hauteur]`. Un polygone
  dégénéré ou auto-intersecté après arrondi est refusé (code `geometry`).
- Baseline : **tous** ses points (polyligne de 2 points ou plus) arrondis de la même façon, dans l'ordre,
  au moins deux points distincts. La fixture 2 en contient un cas à trois points.
- `points="x,y x,y …"`, dans l'ordre canonique des sommets.

La fixture 2 exerce 10,5 → 11, 50,49 → 50, 30,49 → 30, 65,5 → 66, 90,75 → 91, 150,4 → 150,
62,5 → 63 et 82,49 → 82, ainsi qu'un quadrilatère non rectangulaire `11,50 30,50 31,66 10,66`.

## 6. Pertes (rapport par page)
- lisibilité ;
- `char_span` ;
- groupes de césure (tiret visible conservé, pas de `reconstructed_text`) ;
- provenance ; transformations ; `image.sha256`, `color_mode`, `dpi` ;
- extensions : mise en page v2, diagnostics, polices ;
- géométrie sous-pixel ;
- ordre et rattachement des blocs non textuels ;
- `autre` lu comme `texte` ;
- annonce exprimée par recouvrement, et non par identifiant.

## 7. Preuves exigées
1. **Lecteur d'abord.** Le lecteur de test est écrit à partir des seules sections 2 et 4. Avant
   l'existence du producteur, il doit lire :
   - `fixture-1-order.expected.xml` **et** `fixture-1-order.reader-variant.xml`, avec une lecture égale à
     `fixture-1-order.expected-reading.json` ;
   - `fixture-2…expected.xml`, avec une lecture égale à son `expected-reading.json`.
2. **Producteur.** Sa sortie, après analyse avec `remove_blank_text=True` puis C14N 2.0, doit être égale
   au XML attendu des fixtures 1 et 2. La fixture 3 doit lever `free_text_block` sans rien écrire.
3. **Mutations détectées par le LECTEUR INDÉPENDANT** sur le XML attendu de la fixture 1. Chacune doit
   faire diverger la lecture de la lecture attendue, ou produire une erreur de lecture. Le XML attendu
   n'est **pas** le seul juge.

   | Mutation | Effet attendu sur la lecture |
   |---|---|
   | `structure` retiré de `l_p_l00004` | erreur : ligne sans article |
   | `type:heading` retiré de `r_p_b0001` | `kind` = `texte` au lieu de `titre` |
   | `a_p_b0003` réduite à moins de 50 % de r_p_b0003 (par exemple largeur 40 sur 102) | `r_p_b0003.kind` = `texte` ; `advert_ranks` = [] |
   | `a_p_b0003` à exactement 50 % (largeur 51 sur 102, seuil inclusif) | `kind` = `annonce` (cas limite à tester) |
   | Valeurs `index` des `RegionRefIndexed` de `r_p_b0004` et `r_p_b0003` **échangées** (ou leurs `regionRef` échangés), sans toucher à l'ordre physique ; le lecteur trie par `index` | contradiction avec `readingOrder {index}` des TextRegion, donc erreur de lecture contrôlée. Si l'on échange aussi les deux `custom` : ordre `b0000, b0003, b0004, …` et `advert_ranks` = [1], qui divergent de l'attendu |
   | Seul l'ordre **physique** de deux `RegionRefIndexed` échangé, avec index inchangés | **aucun** changement de lecture : c'est un témoin négatif ; le lecteur doit trier par `index` |
   | `index` dupliqué (deux `RegionRefIndexed` à `index="2"`) | erreur de lecture contrôlée |
   | `readingOrder {index}` d'une TextLine supprimé ou dupliqué | erreur de lecture contrôlée |
   | `TextRegion` d'annonce **imbriquée** dans l'AdvertRegion (forme de l'export générique) | `r_p_b0003` absente des régions de premier niveau, ou omise ; `advert_ranks` ≠ [2] |
   | `RegionRefIndexed` visant `a_p_b0003` | erreur : référence d'ordre vers un élément non TextRegion |
   | `custom` en JSON | erreur de grammaire, ou articles absents |
   | identifiant contenant `;` dans `structure {id:…}` | article lu différent de `p_a0002`, ou erreur de grammaire |
   | `RegionRefIndexed` de `r_p_b0004` supprimé | `omitted_text_regions` = [`r_p_b0004`], non vide, donc refus |
4. **Pages réelles**, sans régénération d'image : reprojeter `pilot-v0.2-r2/pages/mf_0003.json` puis
   2 pages v2 (bande et rez-de-chaussée). La lecture conforme est comparée **au canonique**, et non à un
   XML attendu :
   - catégories ;
   - article de chaque ligne ;
   - ordre ;
   - rangs des annonces (pour `mf_0003` : 26 titres, 535 lignes avec article, 14 annonces aux rangs
     3, 4, 24, 32…) ;
   - **chaque** `Word` (identifiant et texte) ;
   - **chaque** point de `Coords` et de `Baseline`, comparé au canonique arrondi par une fonction de test
     écrite depuis le § 5 seul, sans réutiliser le code du producteur.
5. XSD PAGE 2019 sur chaque sortie ; deux exports successifs donnent les mêmes octets.

**Intégration du bundle (Codex, hors producteur pur).** `imageFilename` vaut le chemin relatif de l'image
dans le lot (`images/<id>.png`). Le bundle d'export doit le rendre résoluble vers les PNG copiés, sans
chemin absolu de la source. Le producteur pur ne lit ni ne copie d'image.

Ces conventions (index stricts, refus des listes omises, recouvrement, refus d'ambiguïté) sont celles de
**notre** profil. Elles ne prétendent pas décrire tous les lecteurs NewsEye.

## 8. Question ouverte
Aucune bloquante. La nature exacte de `cover` pour des polygones non rectangulaires ne se pose pas avec
les sorties de ce profil (AdvertRegion = Coords de la TextRegion) ; la définition générale ne sert qu'aux
mutations et aux lectures de documents tiers.
