# Amendement r2.1 à SPEC-A1 révision 2 (la r2 reste inchangée)

Demandé par Codex avant le code : `spec_from_file_location` suivi d'`exec_module`, après un `read_bytes` de
contrôle, peut **relire** le fichier, voire charger un `.pyc`. Le code exécuté ne serait alors pas
nécessairement les octets hachés.

`load_engine(calibrer_path)` doit donc :
1. lire le fichier **une seule fois** (`data = path.read_bytes()`) ;
2. vérifier `sha256(data) == CALIBRER_SHA256`, sinon `RealismError("sha_calibrer")`, sans rien compiler ;
3. créer un module vierge `types.ModuleType("mille_feuilles._calibrer_cadrage")`, donc avec
   `__name__ != "__main__"` : la garde `if __name__ == "__main__"` n'appelle pas `main()` ;
4. compiler **ces octets** (`compile(data, "<calibrer.py sha256:…>", "exec", dont_inherit=True)`), puis les
   exécuter dans `module.__dict__` ;
5. ne **jamais** relire le chemin, ne passer par aucun loader de fichiers, n'écrire aucun `.pyc`, ne pas
   inscrire le module dans `sys.modules`.

Preuves ajoutées :
- **non-relecture** : après le `read_bytes` unique, la lecture du chemin est piégée (open, io.open, os.open,
  Path.open, read_bytes, read_text). L'exécution doit réussir et le compteur de lectures du chemin rester
  à 1 ;
- **aucun `__pycache__`** créé à côté d'une copie de `calibrer.py` placée dans `tmp_path` ;
- un module chargé deux fois donne deux objets distincts, et aucun module de ce nom n'existe dans
  `sys.modules`.
