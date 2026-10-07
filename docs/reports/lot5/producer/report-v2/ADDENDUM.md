# Addendum final — producteur `page-newseye-v1` (contrat du rapport version 2)

Les preuves r1 (`preuve-lot5-producteur/`) et r2 (`preuve-lot5-producteur-r2/`) sont conservées telles
quelles. Seul le **contrat du rapport** change depuis r2 :
- `REPORT_VERSION` passe à `"2"` ;
- les 25 pertes et les 9 notes sont lues dans les `const` du schéma (aucun changement de logique du
  producteur, à part la constante) ;
- un test lie `REPORT_VERSION` au `const` du schéma et vérifie 25 pertes uniques ;
- `docs/EXPORT_NEWSEYE.md` documente les six pertes ajoutées (chemin source remplacé, article des blocs
  non textuels perdu, extensions d'image, de bloc, de mot et d'ordre) et précise que l'ordre physique
  n'est pas promis.

Comme convenu avec Codex, les anciens mutants n'ont pas été rejoués : la logique de projection est
inchangée depuis r2.

## Empreintes (SHA-256), fichiers figés
```
35ebafcc584e5d68b624902738d40fea8b6382b4ebeedb7cbd0079e819e5c3eb  src/mille_feuilles/exports_newseye.py
7df999dfd50025ff142f06d3cb4988ef20942bef07a785427d2bda551d3e1085  tests/test_exports_newseye.py
ebfe65f69e50f1cc2593bbefe7a4c7649994eb0a185346652aab906b7ac463e8  docs/EXPORT_NEWSEYE.md
71f30e32bdfe4b410d27886a03887b3abe0b2f5b53706ce36363acdebaec8c77  schemas/newseye-report.schema.json
```
## Sorties
- `pytest-suite.txt` : 173 passed in 2.17s (producteur et lecteur) ;
- `pytest-pages-reelles.txt` : 3 PASSED (sondes locales facultatives) ;
- `ruff.txt` : All checks passed!
