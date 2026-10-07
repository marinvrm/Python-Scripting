# Lesson 4 — Django

Le tutoriel du cours (application `polls`) et tous les exercices (application
`ynav`), dans un seul projet Django exécuté sur cette machine (Windows 11,
Python 3.13.12, **Django 6.1.2**, dernière version au moment du cours).

```
Lesson 4/
├── requirements.txt          Django 6.1.2 et ses dépendances (pip freeze)
├── questions.json, quiz.py   QCM au format du contrôle (68 questions)
├── revision_lesson4.tex      fiche de révision, à compiler sur Overleaf
├── venv/                     environnement virtuel (non versionné)
└── mysite/
    ├── manage.py
    ├── mysite/               settings.py, urls.py, asgi.py, wsgi.py
    ├── polls/                le tutoriel : Question, Choice, templates
    └── ynav/                 les exercices : pages, formulaires, Pakiman
```

## Lancer le projet

```bash
cd "Lesson 4"
python -m venv venv
venv\Scripts\Activate.ps1         # PowerShell (terminal par défaut de VS Code)
# source venv/Scripts/activate    # Git Bash
# venv\Scripts\activate.bat       # cmd
pip install -r requirements.txt

cd mysite
python manage.py migrate          # crée db.sqlite3 et toutes les tables
python manage.py seed             # optionnel : 5 Pakiman et 2 questions de démo
python manage.py createsuperuser  # pour se connecter à /admin
python manage.py runserver
```

Puis ouvrir <http://localhost:8000/> : la racine redirige vers le sommaire
`/ynav/`, qui contient un lien vers chaque exercice.

Le venv et la base `db.sqlite3` ne sont pas versionnés. Les **migrations**,
elles, le sont : c'est grâce à elles que `migrate` reconstruit la base à
l'identique.

Tests (29, un ou plusieurs par page) :

```bash
python manage.py test
```

---

## Le tutoriel : application `polls`

### Création

```bash
python -m django --version        # 6.1.2
django-admin startproject mysite
cd mysite
python manage.py startapp polls
```

`polls` est déclarée dans `INSTALLED_APPS` sous la forme
`"polls.apps.PollsConfig"`, et branchée dans [mysite/urls.py](mysite/mysite/urls.py)
avec `path("polls/", include("polls.urls"))`.

| URL | Vue | Contenu |
| :-- | :-- | :-- |
| `/polls/` | `index` | questions et choix, HTML construit dans le code |
| `/polls/hello` | `hello` | exercice : `Hello World` dans un `<h1>` |
| `/polls/questions` | `showQuestionsWithTemplate` | même contenu, rendu par un template |

### Migrations

```
$ python manage.py makemigrations polls
Migrations for 'polls':
  polls\migrations\0001_initial.py
    + Create model Question
    + Create model Choice

$ python manage.py sqlmigrate polls 0001
BEGIN;
CREATE TABLE "polls_question" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "question_text" varchar(200) NOT NULL, "pub_date" datetime NOT NULL);
CREATE TABLE "polls_choice" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "choice_text" varchar(200) NOT NULL, "votes" integer NOT NULL,
    "question_id" bigint NOT NULL REFERENCES "polls_question" ("id") ...);
CREATE INDEX "polls_choice_question_id_c5b4b260" ON "polls_choice" ("question_id");
COMMIT;

$ python manage.py migrate
  Applying contenttypes.0001_initial... OK
  Applying auth.0001_initial... OK
  ...                                 <- les apps préinstallées d'abord
  Applying polls.0001_initial... OK
```

On retrouve dans le SQL la clé primaire `id` ajoutée automatiquement et la
colonne `question_id` créée par la `ForeignKey`.

### Django shell

La session du cours, exécutée avec `python manage.py shell` (les modèles ont
déjà leur `__str__`, d'où l'affichage lisible) :

```
>>> Question.objects.all()
<QuerySet []>
>>> q = Question(question_text="What's new?", pub_date=timezone.now())
>>> q.save()
>>> q.id
1
>>> q.pub_date
datetime.datetime(2026, 10, 7, 7, 5, 33, 701547, tzinfo=datetime.timezone.utc)
>>> q.question_text = "What's up?"
>>> q.save()
>>> Question.objects.all()
<QuerySet [<Question: What's up?>]>
>>> q.choice_set.create(choice_text="Choice 1", votes=2)
<Choice: Choice 1 (2 votes)>
```

À noter : `pub_date` est en **UTC** (09:05 à Paris s'affiche 07:05). Avec
`USE_TZ = True`, Django stocke tout en UTC. Les templates convertissent
ensuite dans `TIME_ZONE`, réglé ici sur `Europe/Paris`. La vue `/polls/`,
qui affiche la date via un f-string, montre donc l'heure UTC.

### Admin

`admin.site.register([Question, Choice])` dans
[polls/admin.py](mysite/polls/admin.py). Le modèle `Pakiman` est aussi
enregistré, avec des colonnes, un filtre par type et une recherche par nom.

---

## Les exercices : application `ynav`

Code : [views.py](mysite/ynav/views.py), [urls.py](mysite/ynav/urls.py),
[templates/ynav/](mysite/ynav/templates/ynav/).

| Exercice | URL | Technique |
| :-- | :-- | :-- |
| Hello World en `<h1>` | `/ynav/hello` | `HttpResponse` |
| Profil en HTML complet | `/ynav/user/profile` | `HttpResponse("""...""")` multi-ligne |
| Heure du serveur | `/ynav/time` | `datetime.now().strftime('%H:%M')` |
| Paramètre `p` | `/ynav/query?p=hello` | `request.GET.get("p")` + template |
| Profil par paramètres | `/ynav/query/profile?first_name=John&last_name=Doe` | deux paramètres GET |
| Entiers de min à max | `/ynav/query/range?min=1&max=5` | `range(min, max + 1)` dans un `<ul>` |
| Formulaire `name` | `/ynav/form` | `NameForm(forms.Form)`, POST, `{% csrf_token %}` |
| Table de multiplication | `/ynav/multiplication?n=5` | liste `(i, n * i)` pour i de 1 à 10 |
| Ajouter un Pakiman | `/ynav/pakiman/add` | `ModelForm`, puis redirection |
| Tous les Pakiman | `/ynav/pakiman` | `Pakiman.objects.all()` |
| Pakiman au-dessus d'un niveau | `/ynav/pakiman?level=5` | `filter(level__gt=5)` |

Choix de mise en œuvre :

- **Une seule page Pakiman** sert aux deux derniers exercices : sans
  paramètre elle liste tout, avec `?level=N` elle filtre (strictement
  supérieur, comme demandé).
- **Entrées invalides** : `?min=a`, `?level=abc` ou un `n` absent affichent un
  message au lieu d'une erreur 500. `/query/range` est plafonné à 1 000
  nombres, pour qu'un `?max=100000000` ne génère pas une page de plusieurs Go.
- **Templates rangés par app** (`polls/templates/polls/`,
  `ynav/templates/ynav/`) plutôt que directement dans `templates/` comme dans
  le cours. Django cherche dans les dossiers `templates/` de toutes les apps
  installées : deux fichiers `home.html` dans deux apps se masqueraient l'un
  l'autre.
- **Routes nommées avec espace de noms** (`app_name = "ynav"`) : les templates
  écrivent `{% url 'ynav:pakiman_list' %}` et non l'URL en dur.
- **Échappement** : la vue `/polls/` du cours construit son HTML avec des
  f-strings. `escape()` y a été ajouté : sans lui, une question contenant du
  HTML serait injectée telle quelle dans la page. Les templates, eux,
  échappent automatiquement.

### Bulma et comptes utilisateur

Les pages à template partagent un [base.html](mysite/ynav/templates/ynav/base.html)
qui charge **Bulma** par CDN et affiche une barre de navigation. Les champs de
formulaire reçoivent leur classe CSS grâce à un *template tag* personnalisé,
[templatetags/bulma.py](mysite/ynav/templatetags/bulma.py) :
`{{ field|add_class:"input" }}`. C'est le mécanisme évoqué dans la section
« Registration and Login Forms » du cours.

Les formulaires prédéfinis de `django.contrib.auth.forms` sont branchés :
`/ynav/signup` (`UserCreationForm`), `/ynav/login` (`AuthenticationForm` via
`LoginView`) et la déconnexion depuis la barre de navigation. Depuis Django 5,
`LogoutView` n'accepte plus que le POST, d'où un petit formulaire à la place
d'un lien.

Material Kit (`theme_material_kit`) n'a pas été installé : il remplacerait
Bulma et ajoute une app, des migrations et ses propres routes. Les quatre étapes
du cours sont résumées dans la fiche de révision.

---

## Extensions VS Code recommandées

| Extension | Rôle |
| :-- | :-- |
| `monosans.djlint` | formatage et lint des templates |
| `batisteo.vscode-django` | coloration syntaxique des templates |

```bash
code --install-extension monosans.djlint
code --install-extension batisteo.vscode-django
```

djLint demande en plus `pip install djlint` dans le venv, et que l'interpréteur
Python de VS Code pointe sur `Lesson 4/venv`.

## Réviser

```bash
python quiz.py              # 20 questions, format du contrôle
python quiz.py --themes     # 13 thèmes : URLs, migrations, ORM, templates, forms...
```
