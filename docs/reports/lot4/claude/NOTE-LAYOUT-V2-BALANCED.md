# Relecture Claude — runs/layout-v2-balanced (lecture seule, aucune génération)

Le lot compte 2 pages 1200 × 1656, profil `identity`, même graine. Sources de la relecture :
`pages/*.json`, `qa/mf_0001.png`, et deux extraits de `images/mf_0001.png` (`bande.png` agrandi ×2,
`rdc-bal.png`, tous deux dans ce dossier). Plans revalidés par `layout.check_plan` ; résultat : [] pour
les deux pages.

## Règles de bande (mf_0001, titre large « CHRONIQUE DU THÉÂTRE », span 2)
- Réservation du titre : [42,0 ; 169 ; 595,5 ; 207,187]. L'encre du titre va de x = 42 à 396 : elle
  dépasse une colonne plus la gouttière.
- Bande : [42,0 ; 207,187 ; 595,5 ; 289,359]. Corps : `b0004` (colonne 0, x 42–311,7) et `b0005`
  (colonne 1, x 323,2–593,0), **5 lignes chacun**, de y 207,2 à 280,5 (avant rotation). Il y a donc un bloc
  par colonne, au moins 2 lignes et un écart nul.
- Bas de bande : 289,359 = 280,5 + 0,6 × 14,82 (fin d'article). Les enveloppes finales ne dépassent pas
  le bas de préparation.
- Aucun autre bloc textuel des colonnes couvertes ne commence au-dessus du bas de bande. Les articles
  ordinaires reprennent sous la bande dans les **deux** colonnes ; visuellement, la colonne 1 reprend avec
  « PETITES ANNONCES ».
- Le paragraphe est utilisé en entier et coupé entre colonnes en milieu de phrase (« un catalogue » /
  « par matières »). La dernière ligne de la colonne 0 est justifiée, comme une continuation.
- Le filet entre les colonnes 0 et 1 part sous la réservation du titre et traverse la bande dans la
  gouttière, sans toucher le texte.
- `body_column_indices` vaut [0, 1] ; `attempts` = 1 ; rejets : headline 0, ordinary 0 ; terminaison :
  32 par zone.

## Corps commun
- La typographie vaut main (13 ; 11) et rez_de_chaussee (13 ; 11) : le corps normal est le même dans les
  deux zones. Le rez-de-chaussée à 3 colonnes porte plus de signes par ligne, avec le même corps
  (extrait `rdc-bal.png`).
- `mf_0000` (sans rez-de-chaussée ni titre large) : main (13 ; 11), 1 rejet ordinaire, terminaison 32.

## Remarque mineure (antérieure, hors contrat)
Une ligne d'article peut rester seule en bas de colonne avant de continuer dans la suivante (ligne
orpheline, par exemple au bas de la colonne 0 du rez-de-chaussée de `mf_0001`). C'est le flux colonne par
colonne existant. Limite de réalisme typographique à noter ; pas d'action pour ce lot.

## Portée
Deux pages, une graine, `identity` seulement. Ce n'est ni une estimation de fréquences, ni une revue
×2 ou `controlled`, ni une preuve sur corpus réel. L'acceptation `accept_layout.py` couvre la suite.
