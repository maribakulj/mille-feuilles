# Fixtures originales du profil PAGE NewsEye

Ces attendus ont été saisis par Claude avant tout producteur `project_page`.
SPEC.md, révision 3.1, fixe leur portée ; ils ne revendiquent pas la compatibilité
avec un lecteur externe non exécuté. Les textes sont originaux, sans corpus.

Les quatre pages et leurs spans ont été vérifiés par Codex : validate_page et
validate_text_provenance passent. Les trois XML passent le XSD PAGE 2019 épinglé.
Le lecteur indépendant doit ensuite confronter lecture, mots et géométries
aux attendus, ainsi que les mutations et le témoin d'ordre physique inversé.

SOURCE-SHA256SUMS conserve les empreintes reçues du scratchpad de Claude.
La copie du dépôt modifie seulement deux détails de style Ruff dans les aides
make_canonical.py et make_expected_geometry.py (nom de variable et imports).
Aucun JSON, XML, texte original ou attendu n'est modifié. SHA256SUMS décrit
ces mêmes dix-neuf fichiers dans le dépôt après ces retouches.

Précision de lecture de la table des mutations : retirer une référence sans
renuméroter les indices restants peut produire une erreur d'index avant le
rapport d'omission. Les deux refus sont attendus ; une omission ne doit jamais
être acceptée comme projection conforme.
