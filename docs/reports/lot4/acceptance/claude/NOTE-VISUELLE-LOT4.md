# Revue visuelle Claude — acceptation lot 4 (`runs/accept-layout-v2`, commit 69f0e50)

**Portée honnête.**
- Matériel examiné :
  - `visual/overview.jpg` (7 miniatures de pages) ;
  - 8 extraits natifs de `visual/` : `compact-controlled-x2` mf_0001 (titre large, rez-de-chaussée,
    encadré, petit corps), `compact-identity-x2` mf_0001 (titre large), `pilot-controlled-x2` mf_0000
    (encadré, petit corps) ;
  - les métadonnées des pages (zones, paramètres résolus, comptes de lisibilité des diagnostics).
- Méthode : lecture à l'œil, sans transcription à l'aveugle ni estimation chiffrée de la lisibilité
  humaine. Aucune génération, aucune écriture dans le dépôt.

## Constats de mise en page (conformes)
- Les 7 pages présentent bandeau, colonnes, filets, titres et annonces de façon plausible. `identity` ×1 et
  ×2 sont visuellement indiscernables à l'échelle des miniatures.
- `mf_0001` (compact) :
  - titre large « CHRONIQUE DU THÉÂTRE » sur 2 colonnes ;
  - bande de corps équilibrée sur les deux colonnes ; le paragraphe coupé en milieu de phrase
    (« catalogue » / « par matières ») se lit en continuité ;
  - rez-de-chaussée à 3 colonnes sous un filet pleine largeur, même corps que main ;
  - annonce « RÉPARATION D'HORLOGES » encadrée, cadre fermé.
- Pilote (2 680 × 3 698, colonnes automatiques) : 6 colonnes en main, **sans** rez-de-chaussée ni titre
  large pour cette graine. Encadré (« À LA BIBLIOTHÈQUE / RÉPARATION D'HORLOGES ») et petit corps (« LEÇONS
  DE DESSIN ») bien formés. Les fonctions v2 (rez-de-chaussée, titre large) ne sont donc observées
  visuellement **qu'en compact**.

## Constat principal : étiquettes heuristiques et lecture visuelle divergent fortement sous `controlled-v1`
| Page | Paramètres résolus | readable | uncertain | illegible |
|---|---|---:|---:|---:|
| compact-controlled-x2/mf_0000 | encre 49, papier 249, flou 1,00, érosion 0,39 | 58 | 73 | **2 256** |
| compact-controlled-x2/mf_0001 | encre 16, papier 240, flou 1,23, érosion 0,26 | 57 | 111 | **2 234** |
| pilot-controlled-x2/mf_0000 | encre 49, papier 249, flou 1,00, érosion 0,39 | 2 003 | **3 714** | 233 |
| compact-identity-x1 et x2 (4 pages) | 255 / 0, sans flou | 2 377 à 2 393 | 0 à 2 | 7 à 10 |

- Sur les pages compactes `controlled`, **environ 94 % des mots sont `illegible`**. Pourtant, les extraits
  du titre large, du rez-de-chaussée et de l'encadré restent **lisibles à l'œil**, flous et parfois
  amputés (« CHRON!QUE », « ˌaturelles », « mesure: », « :bservations »).
- Cause probable, cohérente avec la définition déclarée et non mesurée ici : en corps 11 à 13 px avec un
  flou d'environ 1 à 1,2 px, les pixels du masque sont éclaircis au-dessus du seuil de rétention (25 % du
  contraste idéal). La rétention tombe sous 0,3, quel que soit le contraste local.
- C'est le **pendant inverse** de la limite déjà consignée (« mot flou classé lisible » au lot 3). La
  même heuristique classe aussi `illegible` des mots que l'œil lit. Les seuils restent figés ; aucune
  retouche n'est faite ici.
- **Conséquence pratique à documenter** : un consommateur qui filtrerait la supervision sur `readable`
  écarterait presque tout le texte compact `controlled`, et environ deux tiers de la page pilote. Les
  étiquettes `heuristic-v1` ne doivent pas servir de filtre de supervision sans étude dédiée.

## Autres constats
- `controlled-v1` dégrade les pages compactes (corps 11 à 13 px, 67 dpi) bien plus que la taille pilote,
  comme déjà noté au lot 3.
- Les cassures produisent des lettres amputées plausibles. Le petit corps pilote reste lisible malgré
  elles.
- Lignes orphelines en bas de colonne et répétitions de paragraphes : limites connues, sans changement.

## Limites de cette revue
- 7 miniatures et 8 extraits seulement ; une graine ; profils `identity` et `controlled-v1`.
- Aucune transcription à l'aveugle ; « lisible à l'œil » est le jugement d'un seul relecteur sur des
  extraits.
- La cause de la divergence des étiquettes est une explication par la définition, **non** une mesure
  par mot.
