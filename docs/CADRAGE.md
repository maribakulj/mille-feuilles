# Cadrage — heritage-synth (Mille Feuilles)

Rédigé par Claude le 7 octobre 2026, contre le contrat de données **v0.1.0**
(`docs/CONTRAT_DONNEES.md`, commit `f829bd0`). Livré par Claude au coordinateur
dédié Mille Feuilles dans le commit `3a943b5` ; voir
[la passation et les responsabilités actuelles](COORDINATION.md).
Les objections au contrat sont rassemblées au §7 et restent à traiter.
Le contrat n'a pas été modifié lors de cette livraison.

Règles de l'accord, rappelées parce qu'elles commandent tout le reste :

- pilote de 100 pages : presse française du XIXe siècle, priorité à la
  segmentation (blocs, lignes) et à l'ordre de lecture ;
- **calibration sur train/dev seulement, jamais sur un test gelé d'axel** ;
- le synthétique sert aux contrôles et aux diagnostics ; **tout verdict de
  gain se juge sur le réel gelé** (test NewsEye AS, banc de lignes d'E12) ;
- licences vérifiées avant usage ; rien de BBVLM n'est copié.

Outils (bibliothèque standard Python seulement, aucun import d'axel) :

| fichier | rôle |
|---|---|
| `tools/cadrage/calibrer.py` | distributions de mise en page sur les PAGE XML train/dev (§1) |
| `tools/cadrage/fontes.py` | licence, couverture de glyphes et traits OpenType d'une fonte (§3) |
| `tools/cadrage/exemples.py` | vignettes d'exemples réels pour les conventions (§6), hors dépôt |
| `tools/cadrage/sortie/calibration.json` | toutes les distributions, par source et par époque, et chaque page |
| `tools/cadrage/sortie/fichiers_lus.tsv` | **chaque fichier ouvert** par la calibration, avec son SHA-256 |
| `tools/cadrage/sortie/fontes.json` | 64 fichiers Google Fonts et la copie BBVLM d'UnifrakturCook : 65 entrées, 64 empreintes distinctes |

Reproduire (≈ 25 s sur le Mac, CPU, aucun calcul lourd) :

```sh
python3 tools/cadrage/calibrer.py      # lit ~/axel/data/prepared/{olr,seg}
python3 tools/cadrage/fontes.py <dossier de fontes> > tools/cadrage/sortie/fontes.json
python3 tools/cadrage/exemples.py      # vignettes dans ~/heritage-synth-cadrage/exemples/
```

---

## 1. Calibration chiffrée (train et dev seulement)

### 1.1 Pages lues, et preuve qu'aucune page de test ne l'a été

Sources, d'après les manifestes d'axel (lus comme données, sans import) :

| source | manifeste | pages retenues | règle |
|---|---|---:|---|
| NewsEye AS (*Le Gaulois*, *Le Matin*) | `~/axel/data/prepared/olr/newseye_as.json` | 143 (train 123, dev 20) | `split ∈ {train, dev}` |
| KB IMPACT (journaux néerlandais 1618–1885) | `~/axel/data/prepared/seg/manifest.json` | 1 017 | `source = kb`, `split = train`, `excluded = null` |
| BnF « OCR corrigé de presse » | idem | 49 | `source = bnf`, idem |
| NewsEye/READ OCR (BnF) | idem | 44 | `source = read`, idem |
| **total** | | **1 253 pages** | |

Fichiers ouverts : 2 manifestes, 1 253 PAGE XML, et l'en-tête de 187 images
(AS et READ, pour la résolution). **La liste complète, avec le SHA-256 de
chaque PAGE, est `tools/cadrage/sortie/fichiers_lus.tsv` (1 442 lignes).**
Répartition des chemins : `~/corpus-vt/impact-kb-kranten/` 1 017,
`~/corpus-vt/newseye-as/` 286 (143 PAGE + 143 en-têtes), `~/corpus-vt/newseye-read/`
88 (44 + 44), `~/corpus-vt/bnf-presse-seg/` 49.

Garde-fous du script, dans cet ordre :

1. la liste de refus est construite **depuis les manifestes seuls**, avant
   toute ouverture : toutes les pages AS de test (40) et leurs 9 numéros,
   toutes les pages du manifeste de segmentation en `test`, en `dev` hors AS,
   ou `excluded` (315 noms), plus en dur les 12 pages du test d'E12 et leurs
   numéros BnF (`E12_TEST`, `E12_TEST_ISSUES`) ;
2. une page dont le nom, le nom de fichier ou le numéro touche cette liste
   est **écartée sans lecture** ; toute ouverture passe par `Journal.ouvrir`,
   qui s'arrête (`SystemExit`) si on lui présente un fichier refusé ;
3. contrôle final : intersection vide entre pages lues et pages refusées.

Contre-vérification indépendante (après coup, en relisant les manifestes) :
**0 page de test AS lue ; 0 chemin d'une page `test` ou `excluded` du
manifeste de segmentation lu.** Les 40 seuls chemins « hors train » du TSV
sont les 20 pages **dev** d'AS (PAGE + image), autorisées par l'accord.

Deux pages ont été écartées sans lecture par le garde-fou 2 :
`read_6330162-001` et `read_6330162-002`. Elles sont en `train` dans le
manifeste de segmentation, mais **ce sont les mêmes pages que
`bnf_6330162-001/002`, exclues comme « page de test d'E7 »**. Constat pour
axel (pas pour ce projet) : le manifeste E21 garde en apprentissage de lignes
deux pages du test d'E7 ; à signaler au coordinateur d'axel.

### 1.2 Ce que mesurent les chiffres

- Typage des blocs : règle D-231 d'axel, réécrite (annonce si ≥ ½ de la
  surface dans une `AdvertRegion`, sinon tableau si ≥ ½ dans une
  `TableRegion`, sinon titre / légende / texte ; illustration = région
  graphique couverte à moins de ½ par du texte ; `SeparatorRegion` =
  `separateur` ; en-tête, folio, annotation manuscrite = `autre`).
  Intersection exacte si la région couvrante est un rectangle (cas de
  toutes celles lues), approchée sinon.
- Colonnes : regroupement des bords gauches des lignes de texte courant
  étroites (≤ 45 % de la largeur imprimée) ; groupes à moins de 1,5 % de la
  largeur fusionnés, à moins de 6 % aussi (alinéas). Largeur de colonne =
  3e quartile des largeurs de ligne du groupe ; gouttière = écart au bord
  gauche suivant. Contrôlé à l'œil sur deux pages train : *Le Gaulois*
  15/07/1868 p. 2 = 6 colonnes, *Le Matin* 15/01/1886 p. 2 = 5 colonnes,
  conformes au calcul.
- Lignes (AS et READ seulement : seules sources à `TextLine`) : hauteur =
  hauteur de l'enveloppe ; interligne = écart de lignes de base successives
  du même bloc. KB et BnF n'ont pas de lignes : interligne estimé = hauteur
  du bloc / nombre de lignes de son texte.
- Unités physiques : seulement si l'image déclare ≥ 200 dpi. **Les JPEG AS
  du XXe et 30 pages AS du XIXe déclarent 96 dpi, ce qui est faux** (page de
  131 cm) ; ces pages n'entrent que dans les mesures relatives.
- Ordre de lecture : transitions entre blocs successifs de l'ordre de
  vérité (sous le précédent dans la même colonne, en haut de la colonne
  suivante, retour à gauche, etc.). Articles : structure `article` des
  lignes AS (une annonce est un article NewsEye).

Valeurs données en p10 / **p50** / p90 par page (ou par objet), sauf mention.

### 1.3 Résultats

**Profil visé : AS XIXe (65 pages train+dev, 1868–1900).** Colonnes AS XXe,
BnF, READ et KB pour comparaison.

| mesure | AS XIXe (65 p.) | AS XXe (78 p.) | BnF XIXe (16 p.) | READ (44 p.) | KB (1 017 p.) |
|---|---|---|---|---|---|
| colonnes (histogramme) | 2:1, 3:1, 4:2, **5:14, 6:41**, 7:5, 8:1 | 1:3, 2:3, 3:6, 4:5, 5:5, **6:46**, 7:10 | 1:1, 3:2, 4:3, **6:10** | 3:2, 5:7, **6:30**, 7:4, 8:1 | **1:741**, 2:68, 3:58, 4:98, 5:32, 6:17 |
| largeur de colonne / largeur de page | 0,142 / **0,149** / 0,183 | 0,135 / **0,156** / 0,161 | 0,149 / **0,152** / 0,288 | 0,135 / **0,152** / 0,174 | — |
| largeur de colonne (cm, ≥ 200 dpi) | 6,4 / **6,6** / 7,7 | — | — | 4,6 / **6,4** / 6,7 | — |
| gouttière / largeur de page | 0,002 / **0,008** / 0,012 | 0,000 / **0,005** / 0,007 | 0,002 / **0,007** / 0,010 | 0,003 / **0,007** / 0,010 | — |
| gouttière (mm, ≥ 200 dpi) | 2,7 / **4,1** / 5,6 | — | — | 1,3 / **2,4** / 4,0 | — |
| gouttières garnies d'un filet vertical (part, moyenne par page) | **0,88** | 0,90 | 0,81 | 0,07 | 0,56 |
| page (cm, ≥ 200 dpi) | 44,8 × 61,8 / **45,4 × 62,3** / 51,9 × 69,2 | — | — | **41,0 × 57,9** | — |
| rapport H/L | 1,33 / **1,38** / 1,45 | **1,44** | **1,40** | **1,42** | **1,65** |
| interligne (pt, ≥ 200 dpi, 35 p.) | 8,2 / **9,4** / 9,6 | — | — | 5,8 / **7,9** / 9,6 | — |
| interligne / hauteur de page | 0,0042 / **0,0048** / 0,0055 | **0,0048** | **0,0053** (estimé) | **0,0049** | **0,0112** (estimé) |
| hauteur d'enveloppe de ligne / interligne | ≈ **1,4** (enveloppes NewsEye qui se chevauchent) | ≈ 1,4 | — | ≈ 1,1 | — |
| largeur de colonne / interligne | 19,2 / **22,5** / 27,1 | **22,4** | **25,8** (2 p.) | **21,9** | — |
| caractères par ligne de texte courant | 39 / **42** / 48 | 29 / **41** / 45 | — | 35 / **41** / 46 | — |
| lignes finissant par une césure (part) | 0,14 / **0,21** / 0,24 | **0,22** | **0,20** | **0,22** | **0,23** |
| corps relatif titre / texte (hauteur de ligne) | 1,08 / **1,43** / 2,39 (par ligne de titre) | **1,48** | — | — | — |
| largeur d'un titre en colonnes | 0,29 / **0,59** / 0,97 ; > 1,5 col. : **1,3 %** | **0,76** ; > 1,5 col. : 5,9 % | — | — | — |
| marges (enveloppe des régions) G / D / H / B, part de la page | **0,028 / 0,030 / 0,021 / 0,028** | 0,008 / 0,012 / 0,018 / 0,021 | 0,028 / 0,023 / 0,016 / 0,033 | 0,018 / 0,017 / 0,042 / 0,027 | 0,055 / 0,053 / 0,032 / 0,033 |
| zone imprimée / largeur de page | **0,94** | 0,98 | 0,95 | 0,96 | 0,89 |

Types de blocs (part du **nombre** de blocs ; part de la **surface** de page
entre parenthèses) :

| type | AS XIXe | AS XXe | BnF XIXe | READ | KB |
|---|---|---|---|---|---|
| texte | **0,42** (0,74) | 0,28 (0,56) | 0,72 (0,85) | 0,94 (0,96) | 0,70 (0,94) |
| titre | 0,040 (0,018) | 0,049 (0,043) | 0,088 (0,066) | — | 0,15 (0,036) |
| annonce | **0,136** (0,112) | 0,168 (0,173) | — | — | — |
| tableau | 0,100 (0,040) | 0,084 (0,021) | 0,004 (0,052) | ≈ 0 | 0,004 (0,008) |
| illustration | 0,023 (0,050) | 0,043 (0,176) | 0,004 (0,006) | 0,009 (0,033) | 0,022 (0,007) |
| filet (`separateur`) | **0,28** (0,037) | 0,37 (0,026) | 0,18 (0,028) | 0,047 (0,008) | 0,12 (0,011) |
| légende / autre | 0,0003 / — | 0,002 / — | 0,0003 / 0,008 | — | — / 0,003 |

READ ne type pas ses régions (tout est `texte`) ; BnF et KB n'ont pas
d'`AdvertRegion` : l'absence d'annonces y est une absence d'annotation.
`tableau` est gonflé dans AS (les cellules sont des blocs, `docs/e14.md`).

Filets, AS XIXe par page : **94** au total (p10 36, p90 302), dont **27**
verticaux et **60** horizontaux ; la plupart des filets verticaux sont courts
(longueur p50 = 5 % de la hauteur de page, p90 27 %) : NewsEye découpe les
filets de colonne en tronçons. BnF : filets verticaux longs (p50 30 %).

Articles (AS XIXe, structure NewsEye ; 1 834 articles, 533 annonces) :

| mesure | articles | annonces |
|---|---|---|
| par page | 18 / **33** / 57 (articles + annonces) | |
| lignes | 4 / **15** / 65 | 2 / **6** / 34 |
| caractères | 125 / **539** / 2 442 | 62 / **200** / 1 199 |
| blocs | 1 / **5** / 18 | 1 / **3** / 18 |
| colonnes occupées (moyenne) | **1,24** (p90 = 2) | 1,15 |
| avec un titre | **50 %** | 17 % |
| d'un seul tenant dans l'ordre de lecture | **94 %** | 96 % |

Ordre de lecture typique (transitions entre blocs successifs, hors filets
et illustrations) :

| transition | AS XIXe | AS XXe | BnF | READ | KB |
|---|---|---|---|---|---|
| sous le précédent, même colonne | **0,889** | 0,858 | 0,928 | 0,942 | 0,876 |
| en haut de la colonne suivante | **0,058** | 0,065 | 0,045 | 0,037 | 0,053 |
| retour à gauche (nouvelle rangée, sous un titre large) | 0,032 | 0,046 | 0,011 | 0,008 | 0,015 |
| à droite et plus bas | 0,010 | 0,018 | 0,009 | 0,005 | 0,012 |
| remonte dans la même colonne / autre | 0,012 | 0,013 | 0,007 | 0,008 | 0,043 |

### 1.4 Ce que la calibration dit au profil

1. **La presse XIXe de nos données a 5 à 6 colonnes, pas 3 à 5.** *Le
   Gaulois* 1868–1900 : 6 colonnes presque partout ; *Le Matin* 1884–1892 :
   5 ; *Le Matin* 1894–1900 : 6. Seules **17 des 65 pages AS XIXe (26 %)**
   tombent dans 3–5 colonnes, et 14 de ces 17 ont 5 colonnes. READ (6) et
   BnF XIXe (6) disent pareil. Voir l'objection O1.
2. Le texte courant est étroit et serré : ≈ 42 caractères par ligne,
   colonne ≈ 22 interlignes de large, corps ≈ 8–9,5 pt sur une page
   ≈ 45 × 62 cm ; 1 ligne sur 5 finit par une césure. Ces trois nombres
   suffisent à régler la justification et la densité.
3. Les titres sont **petits et dans la colonne** (p50 = 0,6 colonne de
   large, 1,4 fois le corps) ; le titre sur plusieurs colonnes est rare au
   XIXe (1,3 %) et devient courant au XXe. Un générateur « à la moderne »
   (gros titres sur 3 colonnes) serait hors distribution.
4. **Les annonces et les filets ne sont pas marginaux** : 14 % des blocs et
   11 % de la surface pour les annonces, 28 % des blocs pour les filets ;
   88 % des gouttières AS portent un filet vertical. Les détecteurs libres
   d'E12 n'ont pas de classe annonce : le synthétique doit en produire.
5. Un article médian tient en 15 lignes et 5 blocs, la moitié n'a pas de
   titre (brèves, échos) : c'est la cause du plafond de la règle d'articles
   par titres d'E14 (F1 0,57 même à ordre parfait). Le synthétique doit
   reproduire des suites d'articles **sans titre** séparés par des filets
   courts, pas seulement des articles titrés.
6. L'ordre de vérité NewsEye range **article par article** ; 6 % des
   transitions sautent en haut de la colonne suivante. Un article occupe
   en moyenne 1,24 colonne (au moins 10 % en occupent deux ou plus).
7. KB est hors profil (néerlandais, 1618–1885, 1 colonne pour 73 % des
   pages) ; il ne sert qu'au profil « avant 1800 » ultérieur.

---

## 2. Corpus de textes pour remplir les pages

Aucun texte n'a été téléchargé pour ce cadrage. Ce qui suit est le plan.

### 2.1 Sources

| source | contenu | droits | usage proposé |
|---|---|---|---|
| **PleIAs French-PD-Newspapers** ([HF](https://huggingface.co/datasets/PleIAs/French-PD-Newspapers)) | ~3 M numéros Gallica, texte OCR, identifiant Gallica, date, **score de qualité OCR** | déclaré domaine public par PleIAs ; texte issu de Gallica dont la BnF réserve la réutilisation commerciale — **à confirmer sur la fiche avant usage**, preuve à archiver dans `assets.json` | source principale du pilote (vraie langue de presse, annonces comprises) |
| **Wikisource fr** | transcriptions relues de journaux et livres XVIe–XIXe, `ſ` souvent conservé | transcriptions sous **CC BY-SA 4.0** (attribution, partage à l'identique) ; texte sous-jacent du domaine public | texte propre pour le XVIIIe et `ſ` ; à exclure du pilote si la licence BY-SA n'est pas acceptée pour les lots publiés |
| **BnL open data** ([data.bnl.lu](https://data.bnl.lu/data/historical-newspapers/)) | presse luxembourgeoise fr/de, ALTO | **CC0** | complément sans risque juridique ; partie française seulement |
| Chronicling America, titres en français | presse francophone des États-Unis, 1846–1923 | domaine public | diversité lexicale, si besoin |
| BnF ENP « texte » | 17 titres, texte et confiance OCR | conditions Gallica (non commercial) | **non**, sauf accord explicite de Marcel |

Qualité : ne garder que les numéros dont le score OCR de French-PD-Newspapers
dépasse un seuil fixé sur un échantillon relu (proposé : décile supérieur),
puis supprimer les lignes à plus de 5 % de caractères hors alphabet français.
Le texte rendu est exact par construction ; le filtre évite seulement de
composer des suites absurdes (« ap€ès ») qui ne ressemblent plus à du français.

### 2.2 Filtrage anti-fuite vers les tests d'axel

La fuite à craindre : un texte de test d'axel composé dans une page
synthétique, puis appris par un lecteur ou un modèle de langue. Règles :

1. **Par document** (avant toute préparation) : exclure tout numéro dont
   l'identifiant Gallica (ark) ou la date+titre correspond à une page de
   test d'axel : test AS (*Le Gaulois* et *Le Matin*, 9 numéros), test et
   pages protégées d'E12 (`protected_issues` du manifeste de segmentation),
   tests d'E7 (`data/prepared/presse_e7/test.jsonl`, dont des pages
   Wikisource : exclure le **`Livre:` entier**), `icdar2017.test`,
   `icdar2019.test`, `impresso.test`, `bnl.test`, `gallicorpora17/18.test`,
   `ocr17.test`, et `presse_test_manifest.json`. Par prudence, exclure aussi
   les numéros à ± 7 jours de chaque numéro de test des deux titres AS.
2. **Par contenu** : filtre de 8-grammes de mots (normalisation HIPE, comme
   D-232 et D7 d'axel). **Ce filtre doit être calculé côté axel**, qui seul
   a le droit de lire ses tests : axel publie un fichier d'empreintes salées
   (SHA-256 tronqué) des 8-grammes de ses tests ; le générateur rejette tout
   intervalle de texte qui en contient un. Heritage-synth ne voit jamais le
   texte de test. Les bandeaux et annonces récurrents produiront des
   contacts de 1 à 150 8-grammes (vu en E14) : rejeter le paragraphe, pas
   le numéro entier.
3. Traçabilité : chaque `text_span` doit remonter au document source
   (ark ou page Wikisource), pas seulement à l'actif ; voir O13.

### 2.3 Répartition par époque

Pilote (XIXe) : textes de **1830 à 1900**, appariés à la date fictive de la
maquette, 30 % 1830–1869 et 70 % 1870–1900 (la répartition des pages AS XIXe
de train : 1868–1875 et 1884–1900). Orthographe d'origine conservée
(« enfans », « étoient » avant 1835). Ensuite seulement : 1789–1830, puis
avant 1789 (Wikisource, `ſ`), pour le profil ancien où le réel manque
(LITTERATURE §21 : synthétique utile surtout avant 1800).

---

## 3. Fontes

Vérification faite le 7 octobre sur `google/fonts` (commit
`7085eb89a950e85db5b166b7a58d414544b4140c`, copie creuse dans le
répertoire temporaire, non commise) par `tools/cadrage/fontes.py` : table
`name` (licence 13/14), table `cmap` (couverture), traits `GSUB`. Résultat
complet : `tools/cadrage/sortie/fontes.json` (SHA-256 de chaque fichier).
Toutes ces fontes ont un `OFL.txt` à côté du fichier, sauf Ultra
(`LICENSE.txt`, Apache 2.0). Le contrat exige OFL pour le pilote : Ultra est
listée pour mémoire.

Jeux testés : `francais` (accents, Œ, guillemets, tirets) ; `presse_xix`
(fractions ½ ¼ ⅛…, №, §, †, ‰, £, ☞…) ; `ſ` ; ligatures Unicode ﬀ–ﬆ ; les
ligatures sans point de code (ct, st) ne se voient qu'aux traits `liga`,
`dlig`, `hlig`.

### 3.1 Presse du XIXe (pilote)

| fonte | rôle | licence | français | ſ | fractions ⅛ ⅜ | manque (presse) | traits |
|---|---|---|---|---|---|---|---|
| **Old Standard TT** 3.000 | texte courant (« moderne » de labeur fin XIXe) | OFL 1.1 | 100 % | non | oui | ℔ ※ ☞ ☛ ✝ ‖ | liga, dlig ; R / I / B |
| **GFS Didot** 1.0 | texte courant (Didot) | OFL 1.1 | 100 % | oui | oui | № ℔ ※ ☞ ☛ ✝ | liga, hist, onum, smcp ; R seul |
| Libre Bodoni 2.005 | texte, titres | OFL 1.1 | 100 % | non | oui | ℔ ※ ☞ ☛ ✝ ‖ | liga ; R / I |
| Bodoni Moda 2.005 | titres (Didone de titrage) | OFL 1.1 | 100 % | oui | non | fractions fines, ℔ ※ ☞ ☛ ✝ | liga, dlig, hlig, smcp |
| Playfair Display 1.203 | titres | OFL 1.1 | 100 % | oui | partiel | ⅛ ⅜ ⅝ ⅞ ℔ ※ ☞ ☛ ✝ ‖ | liga, dlig, smcp |
| Abril Fatface 1.001 | gros titres, annonces (« fat face ») | OFL 1.1 | 100 % | oui | non | idem | liga, dlig |
| Alfa Slab One 2.000, Zilla Slab 1.1 | annonces (égyptiennes) | OFL 1.1 | 100 % | non | non / partiel | — | liga |
| League Gothic 2.001, Oswald 4.103 | annonces (grotesques étroites, fin XIXe) | OFL 1.1 | 100 % | oui | non | № † ‡ ‰ … | liga |
| Rye 1.001 | annonces fantaisie | OFL 1.1 | 97,7 % (manque des capitales accentuées) | non | non | beaucoup | — |
| PT Serif 1.000 | réserve | OFL 1.1 | 100 % | oui | non | | liga |
| Noto Serif 2.015 | réserve, couverture large | OFL 1.1 | 100 % | oui | oui | ☞ ☛ ✝ seulement | liga, smcp |

Aucune fonte libre vue ne couvre la **main indicatrice ☞** des annonces :
la dessiner comme actif `illustration` ou trouver une fonte de symboles OFL
(non vérifié ici). Les fractions de la Bourse imposent Old Standard, GFS
Didot, Libre Bodoni, EB Garamond ou Noto Serif dans les tableaux.

### 3.2 Époques plus anciennes (après le pilote)

| fonte | licence | ſ | ligatures Unicode | caractères anciens (ꝑ ꝯ ẽ …) | traits | remarque |
|---|---|---|---|---|---|---|
| **IM Fell** (DW Pica, English, French Canon) 3.00 | OFL 1.1 | oui | ﬀ–ﬅ (sans ﬆ) | 21 % | liga, dlig, hist, salt, swsh | fontes Fell du XVIIe ; French Canon pour les titres |
| **EB Garamond** 1.003 | OFL 1.1 | oui | toutes | 71 % | liga, dlig, hlig, hist, swsh, smcp | la plus complète pour XVIe–XVIIIe |
| Cormorant Garamond 4.001 | OFL 1.1 | oui | toutes (italique) / aucune (romain léger) | 50 % | liga, dlig, hlig | |
| Fanwood Text 1.1001 | OFL 1.1 | oui | aucune en Unicode | 36 % | liga, hist | style Fournier (XVIIIe) |
| Linden Hill 1.202 | OFL 1.1 | oui | aucune en Unicode | 36 % | liga, hist | style Deberny (XIXe) |
| Sorts Mill Goudy 003.101 | OFL 1.1 | oui | aucune en Unicode | 36 % | liga, dlig, hist | |
| Gentium Book Plus 6.101 | OFL 1.1 | oui | sauf ﬅ ﬆ | 93 % | liga, smcp | réserve pour l'abréviatif |
| Libre Caslon Text 2.000, Libre Baskerville 2.005 | OFL 1.1 | **non** | sauf ﬅ | 50 % | liga, dlig | XVIIIe anglais ; pas de ſ |
| UnifrakturCook, UnifrakturMaguntia | OFL 1.1 | oui | sauf ﬆ | 14 % | (hlig, liga) | gothique allemande : hors presse française |

Règles qui découlent du contrat (« aucune fonte de substitution ni glyphe
absent ») :

- la préparation du texte **rejette** un intervalle qui contient un caractère
  que la fonte choisie ne couvre pas ; elle ne le remplace jamais ;
- ne pas sous-ensembler ni modifier les fontes : l'OFL interdit d'utiliser
  le nom réservé (RFN) d'une fonte modifiée ; distribuer le fichier tel quel
  avec son `OFL.txt` ;
- `ſ` dans le texte composé ⇒ glyphe `ſ` de la fonte (pas de trait `hist`
  qui transformerait un `s` en `ſ` sans changer la chaîne : glyphe et
  caractère divergeraient).

### 3.3 BBVLM (`~/BBVLM/fontes`) : vérifié, rien copié

Le dossier ne contient qu'**un fichier**, `UnifrakturCook-Bold.ttf`
(42 688 octets, SHA-256 `ea002fa9c65f1a612af100e00d87ab65f16381f450020ec3d021f3dbf79a6dcd`).
Table `name` : « Copyright (c) 2010 j. 'mach' wust with Reserved Font Name
UnifrakturCook. Copyright (c) 2009 Peter Wiegel. This Font Software is
licensed under the SIL Open Font License, Version 1.1 », version
2011-09-01. Le journal de BBVLM (`JOURNAL.md`, l. 1029) dit l'avoir pris sur
Google Fonts. **Le fichier est identique octet pour octet à
`google/fonts/ofl/unifrakturcook/UnifrakturCook-Bold.ttf`.** La licence
Apache 2.0 du dépôt BBVLM ne couvre pas la fonte, et **aucun `OFL.txt`
n'accompagne la copie de BBVLM**. Conclusion : licence compatible, mais ne
pas réemployer cette copie ; prendre la fonte à sa source avec son `OFL.txt`
si un profil en a besoin. Fraktur : hors du pilote (presse française).

---

## 4. Dégradations réalistes

Toutes photométriques ou affines dans le profil 0.1 (`transforms`). Ordre
de priorité, du plus utile au moins utile pour les critères d'axel :

| priorité | dégradation | pourquoi | calibrer sur |
|---|---|---|---|
| **P1** | **échelle et résolution** : rendu à 300 dpi physiques (page ≈ 45 × 62 cm ≈ 5 300 × 7 300 px), puis réduction à 150–300 dpi équivalents, flou de numérisation, JPEG | E11 : les lignes < 35 px font 18–23 % de CER contre ≈ 3 % au-dessus, et une réduction **propre** ne les imite pas (5,6 % sur `syn.dev` contre 18,4 % sur les vraies) : il faut flou + encre + recompressions | hauteurs de ligne px des pages AS/READ train (§1.3 : interligne 24–48 px) |
| **P1** | papier : teinte, grain, jaunissement, inégalité d'éclairage | toutes les pages réelles | histogrammes des images train/dev (non fait ; calcul léger) |
| **P1** | encre : épaisseur variable, lettres cassées, remplissage des contreformes, bavures, impression inégale d'une colonne à l'autre | presse sur papier de pâte, rotative | vignettes train |
| **P1** | transparence (verso en miroir, atténué) | papier journal mince : visible sur la plupart des pages | idem ; le verso doit être une autre page synthétique, tracée dans la provenance (O17) |
| **P1** | inclinaison faible (± 1,5°) et léger décalage | scans à plat mais pas parfaitement droits | lignes de base des pages AS train |
| **P2** | microfilm : contraste dur, quasi bilevel, rayures verticales, poussières, vignettage, flou | une part de Gallica vient du microfilm (dossier `MICRO` de la BnF : **aucune page en train**, donc pas de calibration réelle possible ici) | à décider : sans données train, ne pas en faire une famille principale |
| **P2** | bords : fond du scanner, bords noirs, page rognée, pliure centrale | marges réelles 2–3 % | marges §1.3 |
| **P2** | taches, rousseurs, trous, déchirures | réalisme | — |
| **P3** | **courbure** et déformations non affines | hors profil 0.1 (carte de déplacement à versionner) ; nos scans sont à plat (LITTERATURE §21 : priorité basse) | après le pilote |

Outil de référence pour les effets P1–P2 : Augraphy (licence MIT, à
vérifier à l'intégration), avec chaque paramètre résolu écrit dans
`transforms`. Critère de réalisme (contrôle, pas verdict) : sur un
échantillon train et un échantillon synthétique, mêmes distributions de
hauteur de ligne en px et de contraste encre/papier ; et revue visuelle par
Marcel de planches côte à côte.

---

## 5. Protocole d'ablation (critère gelé avant toute mesure)

### 5.1 Ce qu'on entraîne

Les deux modèles d'E21 d'axel, avec leurs recettes telles qu'elles existent
au moment du gel (`notebooks/colab_seg_train.ipynb`, données
`babaorum/seg/`) :

- **détecteur de blocs** (Heron/D-FINE affiné, classes `titre`, `texte`,
  `legende`, `annonce`, `tableau`, `illustration`, plus filets) ;
- **segmentation de lignes** (`blla` affiné par fenêtres de 1 800 px, D-304).

### 5.2 Trois bras, par modèle

| bras | données d'apprentissage |
|---|---|
| **R** (réel seul) | données E21 actuelles (AS train 123 p., KB, BnF, READ train) |
| **R+S** (mélange) | R + pilote synthétique, mêlés, part du synthétique fixée a priori (proposé : 50 % des échantillons tirés) |
| **S→R** (pré-apprentissage puis affinage) | synthétique seul, puis affinage sur R avec le même budget d'étapes que R |

Même architecture, même résolution d'entrée, même budget total d'étapes
d'affinage sur le réel dans R et S→R ; trois graines par bras si le budget
le permet (budgets indicatifs : ≈ 1 h L4 par bras pour le détecteur sur AS
seul, ≈ 1–3 h pour `blla` ; non engagés). Choix des points (époque, seuil)
**sur le dev AS et le dev d'E12 uniquement**.

### 5.3 Jugement (gelé ici, avant toute mesure)

Une seule lecture de chaque test, par le mécanisme de gel d'E21
(`frozen.json` validé avant toute page de test, un seul modèle par bras,
fiche C4/L3).

| modèle | critère principal | jeu | règle de gain |
|---|---|---|---|
| détecteur | **mAP50 typé (5 classes)** et F1 non typé @0,5 | **test AS gelé** (40 p.) | gain si la différence appariée par page (bras − R) a un IC 95 % bootstrap par page entièrement > 0 **pour le mAP50**, sans perte de F1 non typé au-delà de 0,01 |
| segmentation de lignes | **rappel des lignes de base** (un pour un, D-211) et nombre de lignes coupées | **banc de lignes d'E12** (10 pages à lignes humaines du test) | gain si le rappel moyen monte d'au moins 1 point avec IC par page > 0, sans hausse des coupes |
| chaîne (secondaire) | F de Rostock, succès PRImA, τ des lignes (D-235) | test AS | rapporté, non décisif |

Contrôles et diagnostics (jamais verdicts) : mêmes métriques sur une partie
synthétique tenue à l'écart ; courbe d'apprentissage ; par titre (*Le
Gaulois* / *Le Matin*) et par époque. Résultat nul ou négatif publié tel
quel. Limite connue : le banc de lignes d'E12 est surtout 1937 (7 pages sur
12) et le pilote est XIXe : une absence de gain sur E12 ne réfute pas le
synthétique XIXe ; elle se lit avec la ventilation par page (*La Presse*,
*Le Matin*, *L'Œuvre*).

---

## 6. Conventions à faire valider par Marcel

Vignettes générées par `tools/cadrage/exemples.py` dans
`~/heritage-synth-cadrage/exemples/` (hors dépôt), toutes tirées de pages
**train**. Chaque lien ouvre l'image sur le Mac.

**C1. Qu'est-ce qu'une ligne quand le titre tient sur plusieurs lignes ?**
Question : chaque ligne physique d'un titre est-elle une `ligne` distincte ?
Défaut : **oui**, une ligne par ligne de base, même pour un titre centré de
deux lignes. Exemple : [« DEUXIÈME ACTE / (suite) »](file:///Users/marcel/heritage-synth-cadrage/exemples/titre_multiligne.jpg)
(*Le Gaulois*, 15/07/1868, [page entière](file:///Users/marcel/corpus-vt/newseye-as/img/18680715_1-0001.jpg)).

**C2. Lettrines.** Question : une lettrine est-elle un bloc à part
(`illustration`) dont la lettre reste au début du texte de la première
ligne ? Défaut : **oui** ; la ligne commence par la lettre, son polygone
n'inclut pas la lettrine. Au XIXe, les quotidiens n'en ont presque pas :
proposition d'**exclure les lettrines du pilote**. Exemple : aucun trouvé
automatiquement dans AS XIXe (à montrer plus tard : régions ignorées de KB,
690 lettrines selon C5 d'axel).

**C3. Filets.** Question : un filet est-il un bloc `separateur`, hors de
tout article, sans ligne ? Défaut : **oui**, et il n'entre pas dans l'ordre
de lecture des lignes. Exemple : [filet entre deux articles](file:///Users/marcel/heritage-synth-cadrage/exemples/filet.jpg).

**C4. Mot coupé en fin de ligne.** Question : transcrit-on le trait d'union
tel qu'imprimé (`dissolu-`) plutôt que le signe `¬` qu'emploie la vérité
NewsEye ? Défaut : **le trait imprimé `-`**, avec le groupe de césure du
contrat ; l'adaptateur axel convertit en `¬` si une métrique l'exige.
Exemple : [« dissolu- / tion »](file:///Users/marcel/heritage-synth-cadrage/exemples/cesure.jpg)
(NewsEye transcrit « dissolu¬ »).

**C5. Qu'est-ce qu'une annonce ?** Question : un avis de l'administration
du journal (encadré, signé) est-il une `annonce` ? Défaut : **oui si
NewsEye le met dans une `AdvertRegion`**, sinon `texte` ; une annonce est
un article à elle seule. Exemple : [avis « Le service de distribution du
GAULOIS… »](file:///Users/marcel/heritage-synth-cadrage/exemples/annonce.jpg),
typé annonce par la règle D-231.

**C6. Ordre de lecture d'une page à colonnes.** Question : l'ordre suit-il
les articles (on finit un article, même s'il saute de colonne, avant le
suivant), comme NewsEye ? Défaut : **oui, article par article** ; dans un
article, colonne par colonne de haut en bas. Exemple : [*Le Matin*,
15/01/1886, p. 2, 5 colonnes](file:///Users/marcel/corpus-vt/newseye-as/img/18860115_1-0002.jpg).

**C7. Article qui saute de colonne.** Question : le bloc de la colonne
suivante est-il un bloc distinct du même article, lu juste après ? Défaut :
**oui**, deux blocs, même `article_id`, consécutifs dans l'ordre. Exemple :
[feuilleton « LES ENRAGÉS », fin de colonne puis haut de la suivante](file:///Users/marcel/heritage-synth-cadrage/exemples/saut_de_colonne.jpg)
(*Le Gaulois*, 15/07/1870, [page entière](file:///Users/marcel/corpus-vt/newseye-as/img/18700715_1-0002.jpg)).

**C8. Ponctuation et espaces.** Question : l'espace imprimée avant `;`,
`:`, `!`, `?` et à l'intérieur des guillemets est-elle transcrite par une
espace ordinaire, la ponctuation devenant alors un « mot » isolé ? Défaut :
**oui** (le contrat n'admet que U+0020). Exemple : [« électeurs cette
année ; puis… »](file:///Users/marcel/heritage-synth-cadrage/exemples/ponctuation.jpg).

**C9. `ſ` et ligatures : diplomatique ou normalisé ?** Question : la vérité
garde-t-elle `ſ` (diplomatique), avec une forme normalisée (`s`) seulement
dérivée à l'export ? Défaut : **diplomatique dans le JSON** (le contrat le
dit), `s` dans la vue normalisée ; les ligatures `ct`, `st`, `fi` restent
deux caractères. Exemple : [*Journal de littérature*, 1783, p. 412](file:///Users/marcel/corpus-vt/presse-e7/wikisource/img/ws_Journal_de_Litt_rature_des_Sciences_et_d_fcc3da_p0412.jpg)
(« ſoient », « réflèxion », « &c. »).

**C10. Tableaux.** Question : inclut-on les tableaux simples (cours de la
Bourse) dans le pilote, lus ligne par ligne ? Défaut : **oui, tableaux
simples sans cellules fusionnées**, lus de gauche à droite puis de haut en
bas. Exemple : [bloc tableau](file:///Users/marcel/heritage-synth-cadrage/exemples/tableau.jpg)
(*Le Gaulois*, 15/07/1868, p. 3).

---

## 7. Objections et questions au contrat v0.1.0

**O1 (profil).** `fr_press_19c_columns_3_5` ne correspond pas aux données :
26 % des pages AS XIXe train/dev ont 3 à 5 colonnes, la médiane est 6
(§1.4). Proposition : profil **4–6 colonnes** (ou 5–6 avec 3–4 en
minorité), sans quoi le pilote calibre sur 17 pages et teste sur un autre
domaine.

**O2 (filets dans l'ordre).** §6 : « `reading_order.block_ids` contient
chaque bloc exactement une fois, y compris les non textuels ». Dans NewsEye
et dans axel (`olr_type("separateur") = None`), filets et illustrations ne
sont pas dans l'ordre de lecture ; E21 les sort dans un fichier à part
(`runs/e21/seps/`). Où les place-t-on dans la permutation ? Proposition :
ordre des blocs **textuels** obligatoire, non textuels dans une liste
`unordered_block_ids`, ou position déclarée arbitraire et ignorée à
l'export.

**O3 (annonces et articles).** §4 : `article_id` est `null` « pour un
élément hors article ». NewsEye compte chaque annonce comme un article ; la
mesure de Rostock et le F1 d'articles d'E14 en dépendent. Préciser :
**toute annonce appartient à un article** (souvent d'un seul bloc).

**O4 (convention d'ordre).** Le contrat impose une permutation mais pas sa
règle. La vérité d'axel range **article par article** (E14). À écrire
dans le contrat, avec le cas de l'article qui saute de colonne (C6, C7).

**O5 (enveloppe des lignes).** Le contrat veut l'enveloppe de composition
(ascendantes + descendantes). Les polygones NewsEye sont plus larges et se
chevauchent (hauteur ≈ 1,4 interligne). Les métriques d'E12 reposent sur les
lignes de base, plus l'IoU ≥ 0,5. Demande : (a) définir la ligne de base
comme la **ligne de base typographique** de la fonte ; (b) prévoir à
l'export un polygone « façon NewsEye » (marge déclarée) pour comparer à
armes égales, sans changer le JSON.

**O6 (césure entre blocs).** §6 : le groupe de césure lie deux mots « sur
des lignes consécutives du même article ». Une coupe en bas de colonne
continue en haut de la colonne suivante, donc dans un autre bloc.
Préciser : consécutives **dans l'ordre de lecture**, blocs différents admis.

**O7 (signe de césure).** Le texte diplomatique garde `-` ; la vérité
NewsEye écrit `¬`. Préciser que `-` est la règle et que la conversion
appartient à l'adaptateur (C4).

**O8 (tableaux exclus).** « Les tableaux à ordre ambigu sont exclus » :
les tableaux font 10 % des blocs AS XIXe. Préciser ce qu'est un tableau
non ambigu (C10) ; sinon le pilote a un trou de distribution déclaré.

**O9 (bandeau du journal).** Le titre du journal, la date et l'adresse du
bandeau : `titre`, `autre` ou un article ? NewsEye les met dans un article
(`a2` sur *Le Gaulois* du 15/07/1868, p. 1). À fixer.

**O10 (`separateur` et COCO).** Les catégories COCO 1–8 incluent
`separateur` et `autre` ; E21 entraîne les filets à part (`sep_*`) et
n'émet jamais `autre`. Pas bloquant (l'adaptateur filtre), mais déclarer
dans le rapport d'export que `autre` doit se lire comme `texte` pour l'OLR.

**O11 (taille des images).** PNG RGB à l'échelle réelle (≈ 5 300 × 7 300
px) : ≈ 116 Mo bruts par page, quelques Go pour 100 pages, sur un Mac à
97 % de disque. Admettre `color_mode: "L"` (gris 8 bits), qui est le cas des
pages BnF (44/49 en `GRIS`), et stocker les lots hors du Mac (Drive).

**O12 (lisibilité contrôlée à l'œil).** « Le pilote accepté exige des mots
`readable` après contrôle visuel » : ≈ 5 000–8 000 mots par page, Marcel ne
peut pas les contrôler un par un. Préciser : lisibilité décidée par règle
(seuils de dégradation par mot), contrôle visuel **par page** et par
échantillon de mots.

**O13 (provenance au document).** `text_spans` pointe un actif ; si un
actif regroupe plusieurs numéros (French-PD-Newspapers), l'identifiant du
document source (ark, page Wikisource) doit être retrouvable par intervalle,
sinon le filtre anti-fuite (§2.2) n'est pas vérifiable. Ajouter
`source_document_id` aux intervalles, ou un actif par document.

**O14 (sens des polygones).** « Sens horaire à l'écran » avec y vers le bas
: écrire la règle par le signe de l'aire de la formule du lacet dans le
repère image, pour éviter deux lectures contraires.

**O15 (fichiers de calibration).** `calibration.source_partitions` ne liste
que `train`/`dev`. Demander aussi `{path, sha256}` de la liste des
fichiers lus (ici `tools/cadrage/sortie/fichiers_lus.tsv`), pour qu'un
relecteur prouve l'absence de test.

**O16 (fontes et symboles).** L'interdiction de toute fonte de
substitution est juste, mais aucune fonte OFL vue ne porte ☞ : préciser que
les symboles d'annonces peuvent être des actifs `illustration` placés dans
la ligne, et comment ils apparaissent dans `text` (caractère `☞` attendu
quand même ?).

**O17 (transparence).** La transparence a besoin d'un verso : actif
`illustration` ou autre page du lot ? Le tracer dans `provenance` et
`transforms` (sinon deux pages partagent un contenu sans le dire).

**O18 (résolution).** `dpi` peut être `null`. Pour le pilote, exiger la
résolution physique de rendu **et** celle de l'image finale ; nos JPEG AS
montrent qu'une métadonnée fausse (96 dpi) vaut pire que rien.

**O19 (lettrines).** Un mot appartient à une seule ligne, mais une
lettrine couvre plusieurs lignes. Règle à écrire (C2) ou lettrines exclues
du profil 0.1.

---

## 8. Adaptateur côté axel

Aujourd'hui, ni `scripts/e14_olr_eval.py` ni les mesures de lignes d'E12
(`scripts/e12_report.py`) ne peuvent lire un lot synthétique sans
retouche : chacun a son manifeste codé en dur (`MANIFEST =
data/prepared/olr/newseye_as.json` ; `runs/e12/pages.json`) et des
`--split` limités à `dev`/`test`(/`train`). Ce qu'il faut, côté axel,
dans un chantier séparé (relu comme les autres) :

1. **`scripts/hs_import.py`** (nom provisoire), qui lit `manifest.json`,
   `assets.json` et `pages/*.json` d'un lot, vérifie les SHA-256 et
   `schema_version`, et écrit sans rien perdre :
   - un **PAGE 2019 façon NewsEye** par page : `TextRegion` avec `type`
     (`heading`, `caption`, `paragraph`), `TextLine` avec `Coords`,
     `Baseline`, `TextEquiv` et `custom="readingOrder {index:N;}
     structure {id:<article>; type:article;}"`, `AdvertRegion` et
     `TableRegion` posées sur les blocs `annonce`/`tableau` (pour que
     `axel.olr.page.type_blocks` retrouve le type par la règle D-231),
     `SeparatorRegion`, `GraphicRegion`, un `ReadingOrder` d'un seul
     `OrderedGroup` sur les `TextRegion` ; `¬` en fin de ligne coupée si
     les mesures d'axel le demandent (O7) ;
   - un **fichier de blocs** au format commun
     (`axel.layout.blocks`) : `width`, `height`, `id`, `polygon`,
     `label = category`, `category`, `rank`, `article`, `score = 1.0`,
     pour servir de système « oracle » et pour E21 ;
   - un **manifeste** au schéma de `newseye_as.json` (`page`, `issue =
     source_group_ids[0]`, `title`, `date`, `epoch`, `split = "synth"`,
     `xml`, `image`, `width`, `height`) et une entrée au schéma de
     `runs/e12/pages.json` (`line_geometry: true`).
2. **Options** `--manifest` dans `e14_olr_eval.py` et `--pages-json` dans
   `e12_report.py`, plus la valeur `synth` pour `--split`. Rien d'autre ne
   change dans les métriques.
3. **COCO** pour E21 : depuis le JSON, avec les classes d'`axel.olr.coco`
   (`autre` → `texte`, filets vers `sep_*`), jamais depuis le COCO du lot
   (O10), et le découpage par `source_group_ids` pour ne pas séparer une
   même page synthétique et ses dérivés.
4. **Tests** (fixture du contrat, §8.5) : un aller-retour JSON → PAGE →
   `load_page` qui retrouve identiques catégories, articles, ordre des
   lignes, texte (césures, ligatures, accents, `ſ`), et polygones à 1 px ;
   `e14_olr_eval --system gt-order` sur le lot doit donner 1,000 partout,
   comme sur NewsEye (contrôle de la mesure, E14 §3).
5. **Garde** : `hs_import` refuse un lot dont `calibration.source_partitions`
   contient autre chose que `train`/`dev`, et un lot dont un
   `source_document_id` est dans la liste anti-fuite d'axel (§2.2).

Rien de cela n'est écrit dans axel par ce cadrage.
