# Décisions issues de la revue A1

La SPEC r2 et son amendement r2.1 sont conservés tels que reçus. Les deux
attendus manuels restent inchangés, avec leurs SHA-256 enregistrés dans
`index.json`. Ces précisions complètent le contrat après revue du code :

- Les seuls statuts publics sont C, A, NC et ND. Les pixels relèvent de A
  avec `comparison_allowed: false`, sans statut supplémentaire. Le statut
  de définition demeure visible lorsqu'une observation manquante donne ND.
- Les comparaisons exposent l'unité d'observation et distinguent distributions
  et comptes. Les comptes ne reçoivent ni quantiles ni effectif inventé.
- Une identification de gabarit manquante sur une seule page rend toute la
  cohorte `sans_gabarit` ND : observations partielles conservées, comparaison
  neutralisée. Une liste de gabarit vide est une identification disponible.
- `has_autre` porte sur les blocs effectivement conservés dans chaque variante.
  L'indicateur `ordre_transitions` demeure C : ses classes décrivent des
  déplacements géométriques entre blocs, pas leurs catégories sémantiques.
- D-231 peut reclasser un bloc d'après le recouvrement de ses rectangles
  englobants, même sans intersection polygonale. A1 refuse les reclassements
  ou disparitions inattendus (`category_retyping`), au lieu de conserver une
  comparabilité injustifiée. La conversion déclarée `autre` vers `texte`
  reste admise avec propagation du statut A sur les mesures concernées.
- La note de cohorte décrit les partitions effectivement présentes dans
  les relevés. `as:XIXe` regroupe 53 pages train et 12 dev ; une cohorte
  composée de train seul ne doit pas être décrite comme train/dev regroupés.

L'orchestrateur lit seulement le manifeste natif et les annotations
sélectionnées, les contrôle puis mesure page par page. Les images, exports,
actifs, droits et textes sources ne sont pas revérifiés. Les fonctions pures
historiques s'exécutent depuis des octets épinglés, sans appel au programme
de calibration ni accès aux corpus. Le rapport n'est pas un verdict de
réalisme et ne déclenche aucune modification automatique du générateur.
