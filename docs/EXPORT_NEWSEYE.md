# Export PAGE `page-newseye-v1`

Projection supplémentaire d'une page canonique validée vers PAGE 2019, selon les conventions d'un lecteur
de type NewsEye/Transkribus :
- structure portée par `custom` ;
- articles portés par les lignes ;
- ordre de lecture limité aux `TextRegion` ;
- annonces typées par recouvrement.

L'export générique (`exports/page/`, voir [EXPORTS.md](EXPORTS.md)) reste **inchangé**. Ce profil ne
modifie ni n'importe Axel. Il ne revendique aucune compatibilité avec tout lecteur NewsEye ou Transkribus :
seules les règles écrites dans la spécification normative font foi.

- Spécification normative (révision 3.1) : [tests/fixtures/newseye/SPEC.md](../tests/fixtures/newseye/SPEC.md).
- Fixtures écrites à la main, commitées **avant** le producteur (`135fe97`) : `tests/fixtures/newseye/`.
- Lecteur indépendant, figé avant le producteur (`7c88927`) : `src/mille_feuilles/newseye_reader.py`.
- Contrat du rapport : `schemas/newseye-report.schema.json`.

## API
```python
from mille_feuilles.exports_newseye import NewsEyeExportError, project_page

xml, report = project_page(page, image_filename=None)
```
- `page` : page canonique **validée** (0.2.0 ou 0.3.0). La fonction est **pure** : elle ne lit aucune
  image, n'écrit aucun fichier et ne modifie pas `page`. À page égale, les octets sont égaux.
- `image_filename` : `None` donne `page["image"]["path"]`. Dans tous les cas, la valeur doit être un
  chemin POSIX relatif sûr, avec **la même règle que le lecteur** : aucun `/` initial, aucun `\`,
  **aucun deux-points** (schéma URI, lettre de lecteur), aucun caractère de contrôle U+0000 à U+001F ni
  U+007F, et aucun segment vide, `.` ou `..`. Le bundle de la CLI passe `images/<page_id>.png` et rend ce
  chemin résoluble ; le producteur ne vérifie pas que le fichier existe.
- `xml` : UTF-8 avec déclaration XML, validé par le XSD PAGE 2019 archivé avant d'être rendu.
  L'indentation n'est pas contractuelle : la comparaison se fait après `remove_blank_text` puis C14N 2.0.
- `report` : `format`, `version`, `profile`, `page_id`, `image_filename`, `id_mapping` (identifiants XML
  vers canoniques, clés triées), `not_represented` et `notes`. Ces deux dernières listes sont **lues** dans
  les `const` du schéma de rapport, et non dupliquées dans le code.

## Projection, en résumé (le détail est dans SPEC.md)
| Canonique | PAGE |
|---|---|
| bloc ordonné `titre` / `texte` / `legende` / `autre` | `TextRegion r_<bloc>`, `type` heading / paragraph / caption / paragraph, `custom="readingOrder {index:n;} structure {type:…;}"` |
| bloc `annonce` | `TextRegion` paragraph dans l'ordre, **puis** `AdvertRegion a_<bloc>` sœur, de `Coords` identiques |
| ligne | `TextLine l_<ligne>`, `custom="readingOrder {index:j;} structure {id:<article>; type:article;}"`, avec `Coords`, `Baseline` (tous les points), au moins un `Word` et `TextEquiv` |
| mot | `Word w_<mot>` : `Coords` et texte exact (NFC, tiret de césure visible) |
| filet / illustration | `SeparatorRegion s_<bloc>` / `GraphicRegion g_<bloc>`, hors ordre |
| ordre | `OrderedGroup mf_newseye_order` : `RegionRefIndexed` vers les seules `TextRegion`, dans l'ordre canonique |

Coordonnées : `floor(v + 0,5)` borné à l'image, avec les mêmes refus de polygones dégénérés ou
auto-intersectés que l'export générique.

## Refus contrôlés (`NewsEyeExportError.code`, avant toute sortie)
| Code | Cas |
|---|---|
| `free_text_block` | bloc textuel sans article. Le canonique 0.2.0 l'admet ; c'est **ce profil** qui le refuse, faute de pouvoir exprimer l'article de la ligne. |
| `advert_overlap` | après arrondi, une `AdvertRegion` a une intersection d'aire positive avec une autre `TextRegion`. Règle prudente : la géométrie n'est ni réduite ni déplacée. |
| `table_block`, `category` | catégorie `tableau`, ou inconnue |
| `language` | langue autre que `fr` |
| `custom_value` | identifiant (article, bloc, ligne, mot, page) hors `[A-Za-z0-9_.-]+` ; aucun échappement n'est tenté |
| `reading_order` | ordre canonique incohérent : bloc absent, doublon, bloc non textuel ordonné, bloc textuel non ordonné |
| `empty_line` | ligne sans mot |
| `geometry` | polygone ou baseline dégénérés après arrondi |
| `image_filename` | chemin d'image non sûr |
| `xsd` | sortie non conforme au XSD (garde-fou ; non atteint par les cas testés) |

## Preuves (`tests/test_exports_newseye.py`)
- **Fixtures** :
  - le XML produit est égal au XML attendu écrit à la main (C14N), pour les fixtures 1 (annonce au
    rang 2 sur 5, ordre canonique différent de l'ordre des identifiants) et 2 (Unicode, `&`, césure,
    arrondis, baseline à trois points, quadrilatère non rectangulaire) ;
  - la sortie est valide pour le XSD ;
  - le lecteur indépendant observe exactement la lecture et **chaque point** de la géométrie attendus ;
  - les types de région (`region_types`) et le rattachement des mots (`word_ids_by_line`) sont
    recoupés avec le canonique ;
  - les fixtures 3 et 4 sont refusées avec leurs codes attendus.
- **Refus** : 13 mutations de page et 20 chemins d'image non sûrs (dont `a:b`, tabulation, saut de ligne,
  DEL, NUL) donnent chacun le code attendu. Trois chemins acceptés par le lecteur le sont aussi par le
  producteur.
- **Rapport** : schéma de rapport, `page_id`, `image_filename` égal à l'`imageFilename` lu, bijection
  `id_mapping` ↔ identifiants XML, et nature correcte des cibles canoniques.
- **Pureté** : deux appels donnent les mêmes octets, et la page d'entrée reste inchangée.
- **Pages réelles** :
  - `runs/pilot-v0.2-r2/pages/mf_0003.json` ;
  - deux pages de `runs/accept-layout-v2/lots/compact-identity-x1/` (bande de titre et
    rez-de-chaussée).

  La lecture indépendante est comparée **au canonique** : ordre, catégories, rangs des annonces, article
  et texte de chaque ligne, texte et chaque point de chaque mot, de chaque ligne, de chaque baseline et de
  chaque région, arrondis par une fonction de test écrite depuis la spécification seule. Pour `mf_0003`,
  on retrouve les 26 titres, les 535 lignes avec article et les 14 annonces aux rangs 3, 4, 24, 32…, là où
  le lecteur d'Axel, sur l'export générique, ne voyait aucun titre, aucun article et des annonces en fin
  d'ordre (constat C1 de la [revue Claude](REVUE_CLAUDE.md)).
  **Limite** : `runs/` n'est pas versionné. Ces trois tests sont **ignorés** si les lots locaux sont
  absents ; ils ne s'exécutent pas sur un clone neuf.
- **Mutation du producteur** (contrôle ponctuel, hors suite) : dix producteurs volontairement fautifs sont
  tous détectés :
  - annonce avant son texte ;
  - index de ligne décalé ;
  - arrondi « du banquier » ;
  - contrôle de chevauchement supprimé ;
  - baseline réduite à ses extrémités ;
  - article erroné ;
  - annonce hors de l'ordre ;
  - bloc libre accepté ;
  - chemin d'image non contrôlé ;
  - texte normalisé.

  L'ordre physique « annonce avant son texte » n'est détecté que par la comparaison au XML attendu, car le
  lecteur, à juste titre, ne dépend pas de l'ordre du document.

## Pertes (rapport version 2)
Le rapport porte `version` = `"2"`. La liste **constante** de **25** éléments non projetés et les 9 notes
sont lues dans `schemas/newseye-report.schema.json` (`const`), sans copie dans le code. La version 1, de
19 éléments, a été remplacée avant toute publication : l'audit de Codex y a relevé six omissions.

| Identifiant ajouté en version 2 | Ce qui n'est pas projeté |
|---|---|
| `page.image.path` | le chemin d'image de la page source ; `imageFilename` vaut `image_filename`, `images/<page_id>.png` dans le bundle |
| `page.image.extensions` | les extensions de l'objet image |
| `block.article_id.nontextual` | l'article éventuel des blocs non textuels (filets, illustrations) : leurs régions n'ont aucun `custom` |
| `block.extensions` | les extensions de bloc |
| `word.extensions` | les extensions de mot |
| `page.reading_order.extensions` | les extensions de l'ordre de lecture |

Les 19 identifiants de la version 1 restent valables :
- lisibilité, `char_span`, groupes de césure, provenance, transformations ;
- extensions de page, d'article et de ligne ;
- précision sous-pixel ;
- ordre des blocs non textuels ;
- lien annonce/AdvertRegion par identifiant.

**Ordre physique non promis.** Le document suit l'ordre de lecture pour les `TextRegion` et l'ordre
canonique des lignes et des mots. Cet ordre physique n'est toutefois **pas** une promesse : seuls
`RegionRefIndexed` et `readingOrder {index}` font foi pour l'ordre de lecture, et le lecteur ne dépend pas
de l'ordre du document. L'ordre des tableaux du JSON canonique (`blocks`, `lines`, `words`) n'est pas
reproduit en tant que tel.

Ce qu'une page perd effectivement se recalcule depuis le canonique conservé dans le bundle.
