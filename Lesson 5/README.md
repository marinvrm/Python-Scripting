# Lesson 5 — FastAPI

Le tutoriel du cours (API REST d'utilisateurs avec SQLAlchemy et Pydantic) et
l'exercice (les posts publiés par les utilisateurs), dans une seule API
exécutée sur cette machine (Windows 11, Python 3.13.12, **FastAPI 0.143.0**,
Uvicorn 0.54.0, SQLAlchemy 2.1.4, Pydantic 2.14.1, dernières versions au moment
du cours).

```
Lesson 5/
├── requirements.txt          FastAPI, Uvicorn, SQLAlchemy, pytest (pip freeze)
├── questions.json, quiz.py   QCM au format du contrôle (75 questions)
├── revision_lesson5.tex      fiche de révision, à compiler sur Overleaf
├── venv/                     environnement virtuel (non versionné)
└── api/
    ├── main.py               l'application et toutes les routes
    ├── database.py           engine, SessionLocal, Base
    ├── models.py             tables users et posts (SQLAlchemy)
    ├── schemas.py            schémas d'entrée et de sortie (Pydantic)
    └── test_main.py          28 tests (conftest.py, pytest.ini)
```

## Lancer l'API

```bash
cd "Lesson 5"
python -m venv venv
venv\Scripts\Activate.ps1         # PowerShell (terminal par défaut de VS Code)
# source venv/Scripts/activate    # Git Bash
pip install -r requirements.txt

cd api
uvicorn main:app --reload
```

Puis ouvrir :

- <http://127.0.0.1:8000> : `{"message": "Hello World"}`
- <http://127.0.0.1:8000/docs> : Swagger UI, avec un bouton **Try it out** sur
  chaque route pour envoyer de vraies requêtes
- <http://127.0.0.1:8000/redoc> : la même documentation, en lecture

`uvicorn` doit être lancé **depuis `api/`** : `main:app` est un import Python
(module `main`, variable `app`), et `sqlite:///./test.db` est un chemin relatif
au dossier courant. Lancé ailleurs, Uvicorn s'arrête sur
`Could not import module "main"`. La base `test.db` est créée au premier
démarrage et n'est pas versionnée.

Tests (28, chaque route avec ses cas d'erreur) :

```bash
cd api
python -m pytest
```

Les tests utilisent une base temporaire, jamais `test.db`.

---

## Le tutoriel : les utilisateurs

| Méthode | URL | Effet |
| :-- | :-- | :-- |
| GET | `/` | `{"message": "Hello World"}` |
| GET | `/items/42` | `{"item_id": "42"}` : sans annotation, une chaîne |
| GET | `/items_type/42` | `{"item_id": 42}` ; `/items_type/abc` renvoie 422 |
| POST | `/adduser` | crée un utilisateur |
| GET | `/users` | tous les utilisateurs |
| GET | `/user/{user_name}` | un utilisateur par son nom, avec ses posts |
| PUT | `/user/{user_id}` | modifie un utilisateur |
| DELETE | `/user/{user_id}` | supprime un utilisateur et ses posts |

Session réelle, serveur lancé avec Uvicorn :

```
$ curl -X POST localhost:8000/adduser -H "content-type: application/json" \
       -d '{"name":"alice","email":"alice@example.com","nickname":"al"}'
{"name":"alice","email":"alice@example.com","nickname":"al",
 "url":"http://localhost:8000/user/alice","id":1}

$ curl localhost:8000/items_type/abc
{"detail":[{"type":"int_parsing","loc":["path","item_id"],
  "msg":"Input should be a valid integer, unable to parse string as an integer",
  "input":"abc"}]}
```

### Ce qui a été corrigé par rapport au code du cours

Le code du cours a d'abord été exécuté **tel quel** sur ces versions. Il
fonctionne, mais voici ce qui en ressort :

| Constat sur le code du cours | Correction |
| :-- | :-- |
| `from sqlalchemy.ext.declarative import declarative_base` émet `MovedIn20Warning` | `from sqlalchemy.orm import declarative_base` |
| `class Config: orm_mode = True` émet deux avertissements Pydantic 2 | `model_config = ConfigDict(from_attributes=True)` |
| `GET /users` utilise `UserSchema`, qui n'a pas de champ `id` : la liste ne donne pas les `id` dont `PUT` et `DELETE` ont besoin | schéma de sortie `UserOut` = `UserSchema` + `id` |
| Un email déjà utilisé fait planter `POST /adduser` : `IntegrityError`, **500** | `rollback()` puis **409** avec un message |
| `GET /user/inconnu` renvoie `200` avec `null` | **404** |
| `DELETE /user/abc` : `user_id: str`, donc pas de validation | `user_id: int`, comme dans `PUT` : **422** |
| Deux fonctions `read_item` et deux `get_users` : ça marche (le décorateur a déjà enregistré la première), mais c'est trompeur | un nom par fonction |
| `db = SessionLocal()` dans le `try` de `get_db` : s'il échouait, le `finally` appellerait `close()` sur une variable inexistante | session ouverte avant le `try` |

Autres choix de mise en œuvre :

- **`def` et non `async def` pour les routes qui touchent la base.**
  SQLAlchemy est synchrone : dans une `async def`, chaque requête SQL bloque la
  boucle d'événements, donc tout le serveur. FastAPI exécute les `def` dans un
  thread séparé, ce qui évite ce blocage. C'est ce que fait la documentation
  officielle de FastAPI. Les routes de démonstration (`/`, `/items`) restent en
  `async def`.
- **`check_same_thread=False`** dans `create_engine` : conséquence du point
  précédent, la session peut être utilisée dans un autre thread que celui qui
  l'a créée, et SQLite le refuse par défaut.
- **L'URL de la base est lue dans `DATABASE_URL`**, avec `sqlite:///./test.db`
  par défaut : c'est ce qui permet aux tests de travailler sur une base jetable.
- Le paramètre nommé `url` dans le cours reçoit en fait l'objet `Request`, et
  `request` reçoit le corps JSON. FastAPI ne regarde que les **types** : les
  noms ont été gardés pour coller au cours.

À noter : `create_all` crée les tables manquantes mais **ne modifie jamais une
table existante**. Une colonne ajoutée à un modèle après la création de
`test.db` n'apparaît pas : il faut supprimer `test.db` (ou utiliser un outil de
migration comme Alembic, l'équivalent du `migrate` de Django). Ajouter la table
`posts` à une base existante, en revanche, fonctionne.

---

## L'exercice : les posts

> Chaque utilisateur peut publier des posts. Un utilisateur a plusieurs posts,
> un post appartient à un seul utilisateur. Ajouter les routes GET, POST,
> DELETE et PUT pour les posts.

C'est une relation **un-à-plusieurs**, voir [models.py](api/models.py) :

```python
class User(Base):
    ...
    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    content = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    author = relationship("User", back_populates="posts")
```

- La **clé étrangère** est du côté « plusieurs » : chaque post stocke l'`id` de
  son auteur. `ForeignKey("users.id")` désigne la **table**,
  `relationship("Post")` la **classe**.
- `relationship` n'ajoute aucune colonne : il donne `user.posts` (la liste) et
  `post.author` (l'objet), reliés par `back_populates`.
- `nullable=False` : un post a toujours un auteur. Les colonnes sont nullables
  par défaut, il faut donc l'écrire.
- `cascade="all, delete-orphan"` : supprimer un utilisateur supprime ses posts.
  Sans cascade, SQLAlchemy mettrait `user_id` à `NULL`, ce que `nullable=False`
  interdit.
- SQLite **n'applique pas les clés étrangères** par défaut :
  [database.py](api/database.py) exécute `PRAGMA foreign_keys=ON` à chaque
  connexion.

| Méthode | URL | Corps | Effet |
| :-- | :-- | :-- | :-- |
| POST | `/addpost` | `title`, `content`, `user_id` | crée un post ; 404 si l'auteur n'existe pas |
| GET | `/posts` | | tous les posts |
| GET | `/post/{post_id}` | | un post ; 404 s'il n'existe pas |
| GET | `/user/{user_id}/posts` | | les posts d'un utilisateur |
| PUT | `/post/{post_id}` | `title`, `content` | modifie un post (l'auteur ne change pas) |
| DELETE | `/post/{post_id}` | | supprime un post |

`GET /user/{user_name}` renvoie aussi les posts de l'utilisateur, grâce au
schéma `UserWithPosts`. Les URLs suivent le style du cours (`/adduser`,
`/user/{id}`) : `/addpost`, `/post/{id}`.

Les schémas d'entrée et de sortie sont séparés
([schemas.py](api/schemas.py)) : le client n'envoie jamais l'`id`, généré par
la base, et `PostUpdate` n'a pas de `user_id`, pour qu'un `PUT` ne puisse pas
changer l'auteur d'un post.

---

## Réviser

```bash
python quiz.py              # 20 questions, format du contrôle
python quiz.py --themes     # 11 thèmes : routes, Pydantic, SQLAlchemy, Depends...
```
