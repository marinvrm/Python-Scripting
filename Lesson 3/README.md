# Lesson 3 — Environnements virtuels

Compte-rendu des deux exercices du support `virtual_env.pdf`, exécutés sur cette
machine (Windows 11, Git Bash).

Contexte de départ :

| Outil  | Version   | Emplacement                       |
| ------ | --------- | --------------------------------- |
| Python | 3.13.12   | `AppData/Local/Programs/Python/Python313` |
| conda  | 26.7.2    | `C:\Users\marin\anaconda3`        |

---

## Exercice 1 — venv

Dossier : [exo1_venv/](exo1_venv/)

### 1. Créer un dossier de projet et l'environnement

```bash
mkdir exo1_venv && cd exo1_venv
python -m venv my_env
```

`my_env/` contient `Scripts/`, `Lib/`, `Include/` et `pyvenv.cfg` : c'est la
copie isolée de Python.

### 2. Activer l'environnement

```bash
source my_env/Scripts/activate   # Git Bash
# my_env\Scripts\activate        # cmd / PowerShell
```

Vérification de l'isolation :

```
$ which python
.../exo1_venv/my_env/Scripts/python

$ pip list
Package Version
------- -------
pip     25.3
```

Seul `pip` est présent : aucun paquet du système n'a fuité dans l'environnement.

### 3. Installer des paquets

```bash
pip install requests numpy rich
```

10 paquets installés au total (3 demandés + 7 dépendances tirées
automatiquement : `certifi`, `charset-normalizer`, `idna`, `urllib3`,
`markdown-it-py`, `mdurl`, `Pygments`).

### 4. Vérifier les conflits avec `pip check`

État sain :

```
$ pip check
No broken requirements found.
```

Pour voir à quoi sert réellement la commande, on casse volontairement une
dépendance (`requests` exige `urllib3<3,>=1.26`) :

```
$ pip install "urllib3==1.20"
ERROR: pip's dependency resolver does not currently take into account all the
packages that are installed. ...
requests 2.34.2 requires urllib3<3,>=1.26, but you have urllib3 1.20 which is incompatible.
Successfully installed urllib3-1.20      <-- pip installe QUAND MÊME

$ pip check
requests 2.34.2 has requirement urllib3<3,>=1.26, but you have urllib3 1.20.
# code de retour : 1
```

Point important : pip signale le conflit mais **procède à l'installation**.
`pip check` est l'outil qui relit l'état de l'environnement *après coup*, et son
code de retour ≠ 0 le rend utilisable en CI.

Réparation :

```bash
pip install --upgrade "urllib3>=1.26"   # -> urllib3 2.8.0
pip check                                # No broken requirements found.
```

### 5. Exporter les dépendances

```bash
pip freeze > requirements.txt
```

Contenu obtenu ([exo1_venv/requirements.txt](exo1_venv/requirements.txt)) :

```
certifi==2026.7.22
charset-normalizer==3.5.1
idna==3.20
markdown-it-py==4.2.0
mdurl==0.1.2
numpy==2.5.3
Pygments==2.21.0
requests==2.34.2
rich==15.0.0
urllib3==2.8.0
```

`pip freeze` fige **toute** l'arborescence (dépendances directes *et*
transitives) avec `==` : c'est ce qui rend l'environnement reproductible.

### 6. Désactiver

```
$ deactivate
$ which python
/c/Users/marin/AppData/Local/Programs/Python/Python313/python   # retour au Python système
```

### 7. Reconstruire depuis `requirements.txt`

```bash
rm -rf my_env                     # on supprime tout l'environnement
python -m venv my_env
source my_env/Scripts/activate
pip install -r requirements.txt
```

Contrôle de reproductibilité :

```
$ pip freeze > freeze_check.txt && diff requirements.txt freeze_check.txt
# aucune différence -> environnement reproduit à l'identique

$ pip check
No broken requirements found.
```

---
