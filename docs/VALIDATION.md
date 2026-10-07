# Validation du pilote Mille Feuilles 0.2.0

## Protocole fixé avant production

Le pilote comprend 100 pages de démonstration, 2680 × 3698 pixels à 150 dpi,
graine 20261007, colonnes tirées dans 4–6, dégradations `mixed`, deux workers.
La livraison est produite depuis un commit propre avec Python 3.12 et `uv.lock`.
Les fontes et les trois documents originaux sont ceux du catalogue embarqué.
Aucune page réelle ou donnée de test d'Axel n'est lue.

L'acceptation demande toutes les preuves suivantes :

1. Suite de tests et Ruff sans erreur, actifs vérifiés ; installation depuis un
   clone neuf du dépôt, suivie d'une génération et validation par la CLI.
2. Génération des 100 pages et audit complet : JSON, géométrie, références,
   texte, césures, provenance, licences, empreintes, images et planches QA,
   XSD PAGE/ALTO et relecture des trois exports.
3. Contrôle des pixels de chaque mot sur les PNG finaux. Seuils arrêtés avant
   le calcul : contraste fond local–pixel le plus sombre ≥ 40 niveaux sur 255,
   au moins deux pixels dont l'écart au fond est ≥ 40, police effective ≥ 10 px.
   Ces seuils détectent du contenu absent ou trop faible ; ils ne prouvent pas
   une reconnaissance humaine correcte. Les minima et suspects sont rapportés.
4. Revue visuelle de chaque page sur les dix planches de contact ; examen
   supplémentaire de contours et de recadrages à résolution native couvrant
   colonnes, dégradations, césures, ponctuation et cas les moins contrastés.
5. Reproduction séquentielle des **100 images et 100 JSON canoniques**, depuis
   le même commit, les mêmes actifs et le même environnement que le pilote
   parallèle. Comparaison des octets et SHA-256, sans réécriture des métadonnées.
   Les tests de chaîne prouvent séparément la reproduction de lots complets,
   exports et planches inclus, entre un et deux workers.
6. Archivage des preuves légères dans Git, conservation des lots locaux dans
   `runs/`, puis synchronisation du dépôt GitHub privé.

L'audit de lisibilité et la reproduction sont des preuves distinctes du `pass`
de `mille-feuilles validate`. Un fichier `qa/report.json` préexistant ne dispense
pas d'un contrôle de son contenu et de l'intégrité du lot.

## Résultats

**Pilote accepté le 7 octobre 2026 dans le périmètre défini ci-dessus.**
Commit de production propre :
[`0d1e2b701e9f6ba4d571a5f4894bd40071792225`](https://github.com/maribakulj/mille-feuilles/tree/0d1e2b701e9f6ba4d571a5f4894bd40071792225).
Le lot est `~/heritage-synth/runs/pilot-v0.2-r2` ; sa reproduction est conservée
dans `runs/pilot-v0.2-r2-reproduction`. Les preuves légères sont copiées sans
changement dans [reports/](reports/index.json), avec leurs SHA-256.

| Exigence | Résultat mesuré | Preuve |
|---|---|---|
| Tests | **202 tests passent**, 125,68 s ; Ruff sans erreur sur `src`, `tests`, les deux outils d'acceptation et le vérificateur d'actifs | [Sortie pytest](reports/tests.txt), [commande et sortie Ruff](reports/ruff.json) |
| Installation propre | Clone GitHub neuf au commit de production, Python 3.12.13, installation verrouillée, CLI et actifs conformes ; génération puis validation réussies ; Git propre avant/après, `dirty: false` | [Rapport du clone](reports/clean-checkout.json) |
| Lot complet | **100 pages**, 2680 × 3698 px, 150 dpi ; **209 contrôles PASS**, aucun `fail` ou `not_run` | [Validation complète](reports/pilot-validation.json) |
| Volume annoté | **436 490 mots**, 65 311 lignes, 17 332 blocs, 6 808 groupes de césure | [Statistiques](reports/pilot-statistics.json) |
| Intégrité | **635 artefacts** inventoriés ; empreintes contrôlées aussi par une lecture indépendante | [Manifeste](reports/pilot-manifest.json), [audit indépendant](reports/independent-exports.json) |
| PAGE / ALTO / COCO | Tous les exports passent les contrôles du lot. Relecture XML indépendante sur 7 pages : 29 365 mots et 463 césures. COCO relu indépendamment sur les 100 images et 17 332 blocs | [Audit indépendant](reports/independent-exports.json) |
| Pixels finaux | Les **436 490 mots** sont mesurés, zéro suspect. Minima : contraste **74/255**, **10 pixels d'encre**, police effective **18 px**, contre les seuils 40, 2 et 10 | [Audit de lisibilité](reports/legibility.json) |
| Revue visuelle | Les **100 pages** vues sur les dix planches ; **150 crops** examinés et comparés aux transcriptions par trois relecteurs Codex. Pas d'anomalie bloquante observée | [Couverture et synthèse](reports/visual-summary.json), rapports individuels indexés |
| Reproduction | **100 PNG + 100 JSON**, soit **200 fichiers identiques octet pour octet** ; zéro écart ; environnement strictement identique ; rendu séquentiel comparé au pilote à deux workers | [Rapport de reproduction](reports/reproducibility.json) |

La répartition est de **7 / 33 / 60 pages à 4 / 5 / 6 colonnes**, et de
**22 propres / 50 vieillies / 28 à encre faible**. Les classes produites sont
3 114 titres, 5 673 blocs texte, 1 489 annonces et 7 056 séparateurs. Il n'y a
aucun tableau, illustration, légende ou bloc `autre` dans ce lot.

L'environnement mesuré est macOS 26.4.1 arm64, CPython 3.12.13, FreeType 2.14.3,
Pillow 12.3.0 et moteur BASIC. Les autres versions et empreintes des sources
figurent dans [environment.json](reports/environment.json). L'empreinte du
manifeste de production est
`7c512bdeec4ffa71cc2346f69a073f7f2e4be3f30dafbf6ee7445602d0e6eb71`.

Les planches montrent des marges et gouttières conservées ; les pieds de colonnes
sont volontairement inégaux car un article n'est pas coupé en fin de page.
Les contours de `mf_0029` et le PNG de `mf_0036` ont aussi été examinés directement.
Les crops à ×2 nearest conservent accents, ponctuation et césures ; quelques
fragments voisins apparaissent dans leurs marges sans masquer la cible.
Cette lecture des échantillons ne certifie pas chaque mot du lot ni la lecture
humaine en aveugle à l'échelle native.

![Dix premières pages du pilote](reports/preview.jpg)

## Boucle de correction réellement exercée

La première campagne `runs/pilot-v0.2`, conservée pour diagnostic, a échoué sur
le filet `mf_0029_b0126` : son épaisseur de 1 px permettait la fusion de deux
sommets après rotation et arrondi PAGE. Les filets sont maintenant d'au moins
2 px, dans l'image et le canonique, et le cas exact est un test de régression.
Le contrôle des polygones dégénérés n'a pas été affaibli. L'audit indépendant
confirme les quatre sommets distincts du filet corrigé et contrôle 476 filets
sur les sept pages XML relues.

Une erreur annule désormais les pages encore en attente et laisse finir les
tâches actives avant de remonter l'erreur initiale ; la concurrence et la
préservation de cette erreur sont testées. Le second pilote a été intégralement
produit et contrôlé après ces corrections. Aucun lot n'a été déplacé ou supprimé.

## Commandes de vérification

Depuis le commit de production et l'environnement verrouillé, choisir des
destinations neuves (les chemins ci-dessous existent déjà sur la machine de
mesure) :

```sh
uv sync --locked --python 3.12
uv run --locked pytest -q
uv run --locked ruff check src tests assets/verify_assets.py tools/audit_legibility.py tools/reproduce_pilot.py
uv run --locked python assets/verify_assets.py
uv run --locked mille-feuilles generate --output runs/pilot-v0.2-r2 --pages 100 --seed 20261007 --jobs 2
uv run --locked mille-feuilles validate runs/pilot-v0.2-r2
uv run --locked python tools/audit_legibility.py runs/pilot-v0.2-r2 --report runs/pilot-v0.2-r2-legibility.json --samples-dir runs/pilot-v0.2-r2-word-samples
uv run --locked python tools/reproduce_pilot.py runs/pilot-v0.2-r2 --output runs/pilot-v0.2-r2-reproduction --report runs/pilot-v0.2-r2-reproduction.json
```

La génération appelle déjà la validation complète ; la commande `validate`
permet de la recalculer après transport. Les rapports archivés décrivent cette
exécution, avec ses chemins locaux ; le répertoire `docs/reports` n'est pas un
lot de données. Le script indépendant est conservé tel qu'exécuté depuis `runs/`,
à côté du lot `pilot-v0.2-r2` et de son journal de progression ; les commandes
générales réutilisables sont celles ci-dessus.

## Limites d'interprétation

Les textes sont originaux, synthétiques et répétés : les 100 pages ne sont pas
100 sources indépendantes. Toutes les dérivations d'un document source restent
groupées dans un éventuel découpage aval. Le pilote ne démontre pas la diversité
lexicale, la représentativité historique ou un gain de modèle sur des données
réelles. Aucun entraînement n'est lancé.

La production couvre titres, corps, annonces et filets. Tableaux, illustrations,
lettrines, verso/transparence, déformations non affines et scripts complexes sont
absents. Les dégradations sont légères et les fontes limitées à Old Standard
Regular/Bold dans ce profil. Le moteur de composition BASIC est explicite ; les
ligatures OpenType discrétionnaires ne sont pas activées.
Les césures suivent la largeur de composition, sans dictionnaire syllabique ;
les contrôles garantissent leur reconstruction, pas leur qualité linguistique.

Le fonctionnement validé est celui d'un checkout du dépôt avec l'environnement
verrouillé. La reproduction bit à bit sur un autre système ou avec une autre
version de FreeType/Pillow n'est pas revendiquée.
