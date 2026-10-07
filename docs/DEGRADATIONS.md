# Dégradations mesurées (profil de dégradation 1)

Le profil d'origine (`--degradation clean|aged|faint|mixed`) reste inchangé, octet pour octet. Un
**profil de dégradation** le remplace quand il est demandé. C'est un fichier JSON déclaré
([schéma](../schemas/degradation-profile.schema.json)) dont les paramètres sont tirés page par page, à
partir d'une graine propre à la dégradation. Cette graine (`degradation_seed`) est indépendante de celle
de la composition : à graine de lot égale, deux profils dégradent exactement la même composition.

**Composition constante : entre profils mesurés seulement, et à même `oversampling`.** L'ancien mode
consomme des tirages de composition (mode, papier, encre) avant de composer : à graine égale, il ne compose
pas la même page qu'un profil mesuré. À ×2, les polygones de mots incluent aussi le support des glyphes
rendus au double de la taille : ils peuvent différer légèrement de ceux du ×1.

**`identity` est une identité photométrique**, pas géométrique : la page reçoit toujours sa rotation
(±0,35°), tirée du générateur de composition.

Les profils livrés portent `calibrated: false` (imposé par le schéma). Leurs intervalles sont des choix déclarés, vérifiés
visuellement sur de petites fixtures synthétiques. **Ils ne sont pas calibrés sur des pages réelles.** Une
calibration sur train/dev demandera une décision séparée, prise avec Marcel et Axel.

## Chaîne
1. Le compositeur produit une **couverture d'encre idéale** (float32 dans [0, 1]) : texte à 1, filets à
   200/255. Il y applique **toutes** les transformations géométriques : rotation et, si `oversampling` = 2,
   réduction ×2 → ×1 par `degrade.downsample_coverage` (moyenne exacte par blocs). La réduction porte sur la
   **couverture grise**, avant le seuillage du masque ; un masque booléen n'est jamais réduit (testé).
2. Le **masque idéal** est la couverture ≥ 0,5. Il est enregistré en PNG 1 bit, avant toute altération
   photométrique : l'encre perdue ou ajoutée reste donc mesurable.
3. `degrade.apply` applique les familles dans un ordre fixe, chacune avec son propre flux numpy
   `PCG64([graine, famille])` :

| Famille | Paramètres | Effet exact |
|---|---|---|
| `ink_loss` | `erosion` ∈ [0, 1], `break_density` ∈ [0, 0,5], `break_scale_px` ∈ [0,5, 8] | mélange vers l'érosion grise 3×3 dans la proportion `erosion`, puis mise à zéro d'une fraction `break_density` des pixels d'encre (≥ 0,5), choisie par un bruit uniforme lissé (flou gaussien de rayon `break_scale_px`) |
| `contrast` | `paper_level`, `ink_level` (encre < papier) | image = papier − (papier − encre) × couverture ; famille absente = 255/0 |
| `illumination` | `amplitude` ∈ [0, 80], `direction_degrees` | dégradé linéaire de −amplitude/2 à +amplitude/2 selon la direction |
| `blur` | `sigma_px` ∈ [0, 5] | `GaussianBlur` de Pillow sur l'image 8 bits |
| `noise` | `sigma` ∈ [0, 30] | bruit gaussien additif, arrondi et écrêté dans 0–255 |

`check_profile(profil)` valide un profil en mémoire. Il refuse les valeurs non JSON, NaN, infinies, les
entiers hors des flottants finis et toute valeur hors des bornes ; `load_profile` le réutilise.
`check_parameters(paramètres)` valide les paramètres résolus, tels qu'une page les stocke : clés et
familles connues, graine entière dans 0..2^64−1, valeurs finies dans les bornes, encre plus sombre que le
papier. `apply` et `diagnostics.measure` l'appellent avant tout calcul. Un refus est une `ProfileError`,
jamais une exception brute.

Chaque famille active ajoute à `transforms` un enregistrement `mf:degrade:<famille>`, de géométrie identité,
avec ses paramètres résolus et sa graine.

## Diagnostics (`qa/diagnostics/<page>.json`)
Le masque est écrit dans `qa/masks/<page_id>.png` (`diagnostics.mask_path`), en PNG mode `1`, encre en
blanc. Le document est écrit dans `qa/diagnostics/<page_id>.json` (`diagnostics.diagnostics_path`). Il
vaut `diagnostics.document(...)`, c'est-à-dire le résultat de `measure()` complété de `inputs.image` et
`inputs.mask` (`path`, `sha256`). Le validateur relit ces deux fichiers, vérifie leurs empreintes,
recalcule le document et applique `compare()`, qui exige une égalité exacte (valeurs arrondies à 6
décimales).
Les mesures, recalculées par le validateur, partent de l'image finale, du masque idéal et des polygones.
- **Papier** : pixels à plus de 2 px du masque.
- **Encre** : pixels du masque.
- **otsu_threshold** : seuil d'Otsu de l'image entière.
- **ink_loss_fraction** : part du masque au-dessus de ce seuil.
- **spurious_ink_fraction** : part du papier au-dessous ou au niveau du seuil.
- **noise_mad_sigma** : 1,4826 × MAD du papier.
- **edge_contrast_proxy** : gradient moyen au bord du masque, divisé par le contraste ; **indicateur
  relatif, pas une mesure physique du flou**.

**Mot** (polygone exact, rasterisé dans sa boîte) :
- papier local : médiane du papier dans le polygone, ou médiane de la page s'il y a moins de 16 pixels ;
- encre : 10e centile du masque ;
- contraste : papier local − encre ;
- **rétention** : part des pixels du masque qui conservent au moins 25 % (`RETENTION_CONTRAST_SHARE`) du
  contraste idéal, c'est-à-dire du papier local à l'encre de référence déclarée par le profil
  (`contrast.ink_level`, 0 par défaut).

## Lisibilité heuristique (`legibility_method: heuristic-v1`)
| Étiquette | Pixels de masque | Contraste | Rétention |
|---|---|---|---|
| `readable` | ≥ 2 | ≥ 40 | ≥ 0,60 |
| `uncertain` | ≥ 1 | ≥ 20 | ≥ 0,30 |
| `illegible` | sinon | | |

Ces étiquettes sont des **heuristiques** déclarées. Elles ne valent pas lecture humaine : aucune
équivalence n'est démontrée. **`heuristic-v1` ne certifie pas qu'un mot est une supervision OCR
valable.** Exemple conservé (planche des fixtures, graines 0, 2 et 6 de `controlled-v1`) : « municipal »,
« canal », « animée » ou « dimanche », amputés d'une partie de lettre par les cassures, restent
`readable`, alors qu'une lecture pourrait y voir une autre lettre. Les seuils de `heuristic-v1` sont figés
pour la campagne d'acceptation du lot 3.

**Historique honnête.** Deux définitions ont changé avant toute mesure de lot, après examen visuel de
planches de fixtures synthétiques :
- **Rétention.** La règle initiale, « pixel plus sombre que le milieu entre papier et encre de référence »,
  classait illisible un texte nettement lisible flouté de 1,1 px. Elle a été remplacée par la règle des 25 %
  du contraste.
- **Érosion.** L'érosion entière de 1 px (3×3) effaçait le corps de 22 px : elle est devenue fractionnaire.

## Limites connues
- **Masque falsifié mais cohérent.** Le validateur ne re-rend pas la page. Si un masque est remplacé et
  que ses empreintes et ses diagnostics sont recalculés, le recalcul reste cohérent avec ce faux masque :
  les mesures et les SHA-256 **ne prouvent pas** que le masque correspond aux glyphes rendus. Seules la
  reproduction déterministe de la génération et les tests du rendu confrontent le masque au dessin.
- **Signe visible sans pixel de masque.** Constaté à l'acceptation du lot 3 (`cb24e39`). Sous `identity`,
  des tirets visibles sont classés `illegible` avec `ink_pixels = 0` : leur couverture idéale reste sous le
  seuil de 0,5 du masque. Un signe peut donc être visible sans fournir assez de pixels au diagnostic.
- **Mot flou classé lisible.** Constaté à la même acceptation. Sous `controlled-v1`, des mots proches des
  seuils restent très flous tout en étant classés `readable`. Pour un même profil, le corps de 10 px des
  pages compactes est bien plus atteint que le corps de la taille pilote.
  Ces deux constats viennent d'un sondage visuel (6 miniatures, 17 extraits de mots), sans transcription
  à l'aveugle ni estimation de la précision des étiquettes. Preuve :
  [note visuelle](reports/lot3/acceptance/reports/visual-review.json). Les identifiants et rectangles
  exacts des extraits sont dans [la sélection](reports/lot3/acceptance/visual/selection.json).
  **Les seuils de `heuristic-v1` restent figés** : aucune retouche après inspection.
- **Mot lisible à l'œil classé illisible.** Constaté à l'acceptation du lot 4 (`69f0e50`) ; c'est le
  pendant inverse de la limite précédente. Sous `controlled-v1` ×2, sur les deux pages compactes
  (corps 11–13 px), les **étiquettes mesurées** sont `illegible` pour 2 256 et 2 234 mots sur environ
  2 390. Paramètres résolus : encre 49 et 16, flou 1,00 et 1,23 px, érosion 0,39 et 0,26. À la taille
  pilote, avec les mêmes paramètres que la première page compacte, on compte 2 003 `readable`,
  3 714 `uncertain` et 233 `illegible`.
  - Un **sondage visuel** (8 extraits natifs, un relecteur, sans transcription à l'aveugle) trouve ces
    passages compacts flous et parfois amputés, mais déchiffrables à l'œil.
  - Cause **supposée, non mesurée mot par mot** : un flou d'environ 1 px éclaircirait les pixels du
    masque au-delà du seuil de rétention (25 % du contraste idéal), ce qui ferait passer la rétention
    sous 0,3.
  - Les étiquettes `heuristic-v1` ne sont donc pas des jugements de lisibilité humaine. Aucun usage de
    `heuristic-v1` seul comme filtre de supervision n'est recommandé.
  - Preuves : `docs/reports/lot4/acceptance/claude/NOTE-VISUELLE-LOT4.md` et `visual/selection.json`
    de la même archive. **Les seuils restent figés.**
- **Lettres cassées.** Une lettre partiellement effacée par les cassures (« m·nicipal ») laisse le mot
  `readable`, car sa rétention globale reste haute. L'heuristique ne détecte pas les substitutions
  plausibles de lettres.
- **Bruit écrêté.** Sur un papier à 255, la moitié du bruit est écrêtée et `noise_mad_sigma` le
  sous-estime (testé).
- **Monotonie.** Elle n'est vérifiée que par des balayages contrôlés à un seul paramètre sur une fixture ;
  aucune monotonie générale n'est revendiquée.
- **Absents de ce profil.** Pas encore de verso ni de transparence, de réduction de résolution, de JPEG, de
  microfilm ni de courbure.
- **Coût mesuré** sur une page 2 680 × 3 698 de 5 349 mots, construite en mémoire : `apply` ≈ 0,6 s,
  `measure` ≈ 0,65 s (Mac de mesure, CPython 3.12).
