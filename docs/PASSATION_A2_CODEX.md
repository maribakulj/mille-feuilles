# Passation Codex → Claude — Mille Feuilles — 8 octobre 2026

Marcel demande que tu reprennes seul la coordination et la poursuite de Mille Feuilles : il n’a plus assez de crédits API pour continuer avec Codex. Il avait demandé d’achever le tour A2 puis de transmettre tout le travail Codex que tu n’avais pas vu. Il a ensuite écrit « stop » : le développement Codex s’est arrêté immédiatement. Ce document transmet l’état réel, sans présenter A2 comme accepté.

## État à la passation

- Dépôt : `/Users/marcel/heritage-synth`, branche `main`, dernier commit A1 connu `178a79b785057d63508be4854e6b85adb56dc974` (preuves A1). La tête n’a pas été avancée pour A2 ; aucun commit/push A2.
- Le worktree A2 est sale et doit être préservé. Modifiés : `schemas/manifest.schema.json`, `schemas/page.schema.json`, `src/mille_feuilles/cli.py`, `pipeline.py`, `render.py`, `validation.py`, `tests/test_layout_render.py`, `tools/reproduce_pilot.py`, `tests/test_content_pipeline.py`. Nouveaux fichiers : `docs/COMPOSITION.md`, `src/mille_feuilles/content.py`, `tests/test_content.py`, `tests/test_content_pipeline.py`, `tests/test_content_render.py`, `tests/test_content_validation.py`.
- Lot exploratoire réellement généré et validé : `runs/content-a2-first` (deux pages miniatures, quelques Mo), sans suppression ni déplacement. Les 17 contrôles CLI sont passés : reçu et profils, deux pages, fichiers, inventaire et exports. Statistiques : 26 articles de corps, 9 fenêtres de 2 unités et 17 de 3, 5 333 mots sur les deux pages. Une inspection rapide de la planche paraît plausible ; aucune revue visuelle formelle ni mesure OCR.
- Le générateur a été lancé avec :
  `uv run --locked --offline mille-feuilles generate --output runs/content-a2-first --pages 2 --width 1200 --height 1656 --dpi 67 --columns 4 --seed 20261007 --degradation-profile identity --layout-profile fr_press_19c_layout_v2 --content-profile consecutive-v1 --jobs 1`
- Test ciblé du rendu : `10 passed in 81.18s` (fichier `tests/test_content_render.py` et non-régression du rendu v2). Les tests A2 de contenu/validation avaient passé séparément, mais pas encore une suite intégrée complète après tous les raccords. Après le test, Codex a ajouté un refus de reçu `mf:content_profile` orphelin dans `tools/reproduce_pilot.py` et élargi le test de reproduction correspondant ; **ces deux derniers changements n’ont pas été testés**.
- La réserve disque observée était 2,2 Go. Garder au moins 500 Mo libres. Aucun nettoyage n’a été fait ni autorisé.
- La campagne complète `/private/tmp/mf-accept-content/tools/accept_content.py` **n’a pas été lancée**. Son SHA avant les deux remarques de revue était `ae4d485556ce5780882fcc904f4bb83b9e789f381306fa0d33d4b48b9142243a`. Elle doit encore être revue/corrigée avant exécution : `composition(geometry=False)` conserve `article.extensions['mf:layout'].box.bbox`, dérivé des enveloppes d’encre et légitimement différent entre ×1 et ×2 ; enlever ce seul champ de la signature sans géométrie, en gardant cadre/padding/rule_ids. Le rapport copie `statistics.content` du validateur sans recomptage indépendant : reconstruire `articles`, `units_per_article` et `body_documents` depuis les observations vérifiées puis comparer. Vérifier les longueurs de baseline et polygones avant les `zip`.
- La preuve historique comparative contre `178a79b` **n’a pas démarré** ; `/private/tmp/mf-a2-historical` n’existait pas lors du contrôle. Elle ne fait pas partie de la preuve A1/lot 3/lot 4 déjà archivée.

## Ce qu’A2 ajoute

`consecutive-v1` est une option explicite de génération, uniquement avec `fr_press_19c_layout_v2` et un profil de dégradation explicite. Elle sélectionne un document de rôle `body` éligible, puis uniformément 2 ou 3 unités consécutives, puis une fenêtre complète uniforme. Elle ne tronque pas pour faire tenir le texte. Les refus géométriques rejettent le candidat entier. Au moins un article multi-unité doit être effectivement composé par page. Sans option, sérialisation et tirages historiques restent inchangés.

Chaque article reçoit `mf:source_sequence` (asset, bornes Unicode, intervalle d’unités) ; le corps garde un seul span couvrant tous ses blocs. Le titre reste tiré séparément. `manifest.extensions['mf:content_profile']` contient un reçu inline recalculable sur les textes copiés ; le profil de page et le reçu sont contrôlés. Les unités gardent les fins de ligne universelles de `Path.read_text`, tandis que SHA porte sur les octets originaux. Référence complète : `docs/COMPOSITION.md`.

Le sélecteur et son contrat sont dans `src/mille_feuilles/content.py`. Le rendu/RNG et la provenance sont dans `render.py`. Schémas, validation de page/source, reçu exact et contrôle d’unités sont dans `validation.py`. Pipeline/CLI et stats sont dans `pipeline.py` et `cli.py`. La reproduction reprend `content_profile` et contrôle le reçu préalablement à la destination.

Les limites qui restent fondamentales : le catalogue embarqué n’a qu’un document de corps de démonstration ; unités consécutives n’impliquent pas cohérence d’article historique ; les blancs d’alinéa sont aplatis ; placement peut biaiser les distributions tirées ; aucun gain OCR/OLR/apprentissage, réalisme historique ni diversité de sources n’a été démontré. Aucun corpus réel n’a été ouvert. Aucun contact ni changement de dépôt Axel n’est autorisé par ce lot.

## Revue A1 reçue maintenant

Ta revue en lecture seule de `178a79b` a trouvé les 101 tests A1 ciblés passants dans le venv du dépôt (`test_realism`, `test_structure_report`, `test_structure_cli`). Tu confirmes que `category_retyping` ne présente pas de défaut : comparaison des seuls blocs conservés, seul `autre → texte` autorisé, avant mesure, sans faux refus sur `AdvertRegion`. Une région invalide de moins de trois points est explicitement refusée. Les cohortes/splits et le statut NC `annonce_avec_titre` sont cohérents ; aucun blocage A1. Tes scratchpads doivent rester figés.

Le rapport/campagne A1 déjà accepté est versionné sous `docs/reports/a1/`; commit source `5ad97b4`, commit de preuves `178a79b`. Son acceptation a passé 670 contrôles, pour quatre annotations historiques synthétiques existantes. C’est descriptif uniquement, aucune conclusion de gain de modèle. Les essais A1 n’utilisent pas de nouveau corpus ni de pixels recalculés.

## Suite à prendre en charge

1. Vérifier le worktree avant toute action : `git status --short`, `git diff --check`. Ne pas écraser/réinitialiser les modifications A2 ni supprimer les lots existants.
2. Traiter le refus orphelin de reproduction déjà commencé dans `tools/reproduce_pilot.py` + `tests/test_content_pipeline.py`. Lancer au minimum ce test ciblé et Ruff, puis la suite A2 et la suite complète appropriée avant gel.
3. Lire `content.py`, les changements intégrés et les quatre tests ; refaire la revue contradictoire du script d’acceptation ci-dessus. Corriger uniquement après avoir constaté l’état effectif des fichiers scratch.
4. Si l’arbre est cohérent, commit source propre. Ensuite seulement exécuter l’acceptation bornée prévue par le script (huit pages totales avec rejeu/reproduction, 200 Mo écrits maximum, réserve réelle 500 Mo). Le script déclare explicitement que le budget est vérifié entre commandes, pas comme quota atomique.
5. Inspecter manuellement les images du lot et archiver quelques preuves légères. Une revue visuelle ne prouve pas la lisibilité mot à mot. Compléter séparément la preuve d’anciens modes sans option par rapport à `178a79b`, si elle demeure utile et si le disque suffit.
6. Mettre à jour les docs communes/journal/coordination avec les limites ci-dessus, commiter les preuves, pousser, vérifier l’empreinte distante. Garder explicitement « évaluations OCR/utilité et corpus autorisés en attente ».
7. Continuer ensuite A2/A3 selon les résultats ; ne pas clore le projet. Les décisions d’exclusions et les corpus Axel restent sous coordination Axel.

## Dépendances et coordination

Les deux sous-agents Codex utilisés pour cette fin de tour ont atteint leur quota, aucun livrable nouveau ne leur est à demander. Ton propre quota Claude semblait atteint avant ton récent retour, mais tu as maintenant transmis la revue A1 ; si tu reprends les modifications, confirme d’abord que tu peux continuer. Marcel a indiqué manquer de crédits Codex : ne compte pas sur une réponse Codex ultérieure. Fais-lui des mises à jour concises et garde les constats/revues croisés. Cette passation ne transfère ni le projet Axel ni ses données sous ta coordination.
