# Python Scripting

Un dossier par cours, et dans chaque dossier un QCM interactif pour réviser le
cours de la semaine avant le contrôle.

## Lancer un QCM

Depuis le dossier de la leçon :

```bash
cd "Lesson 1"
python quiz.py
```

Ou depuis la racine du dépôt :

```bash
python run_quiz.py              # menu des leçons
python run_quiz.py "Lesson 1"   # directement
python run_quiz.py 1 -n 10      # par numéro, avec options
```

Aucune dépendance à installer : uniquement la bibliothèque standard, Python 3.8+.

## Options

| Option | Effet |
| :-- | :-- |
| `-n 10` | nombre de questions (20 par défaut) |
| `-t listes -t dict` | filtre par thème, répétable, recherche partielle |
| `-d 3` | filtre par difficulté (1, 2 ou 3), répétable |
| `--revision` | rejoue uniquement les questions ratées la dernière fois |
| `--themes` | liste les thèmes de la leçon et leur nombre de questions |
| `--ordre-fixe` | ne mélange pas l'ordre des réponses |
| `--seed 42` | rejoue exactement le même tirage |
| `--help` | toutes les options |

Pendant le QCM : une lettre (`a`) ou un chiffre (`1`) pour répondre, `a,c` pour
les questions à plusieurs réponses, `s` pour passer, `q` pour quitter. Chaque
réponse est corrigée immédiatement avec une explication, et le bilan final
détaille le score par thème.

Les questions ratées sont mémorisées dans un fichier `.quiz_history.json` local
(non versionné), ce qui permet de les rejouer avec `--revision`.

## Structure

```
Python Scripting/
├── quiz/                 moteur partagé par toutes les leçons
│   ├── engine.py         chargement, validation, tirage, correction
│   └── cli.py            affichage terminal et boucle interactive
├── run_quiz.py           lanceur depuis la racine
├── nouvelle_lecon.py     crée le dossier de la semaine suivante
└── Lesson 1/
    ├── Lesson1_Bases.ipynb
    ├── Lesson1_Exercise_Part1.ipynb
    ├── Lesson1_Exercise_Part2.ipynb
    ├── questions.json    la banque de questions de la leçon
    └── quiz.py           lanceur local
```

## Ajouter une leçon

```bash
python nouvelle_lecon.py "Lesson 2"
```

Le dossier est créé avec son `quiz.py` et un `questions.json` de départ. Il ne
reste qu'à y déposer les notebooks du cours et à écrire les questions.

## Écrire des questions

`questions.json` contient une liste de questions. Le format minimal :

```json
{
  "lesson": "Lesson 2",
  "title": "Programmation orientée objet",
  "questions": [
    {
      "id": "l2-poo-01",
      "topic": "Classes",
      "difficulty": 2,
      "question": "Que représente self dans une méthode ?",
      "code": "class Chien:\n    def aboyer(self):\n        print(\"Wouf\")",
      "options": ["L'instance courante", "La classe", "Le module", "Rien"],
      "answer": 0,
      "explanation": "self est passé automatiquement à l'appel."
    }
  ]
}
```

| Champ | Rôle |
| :-- | :-- |
| `id` | identifiant unique, sert à mémoriser les questions ratées |
| `topic` | thème affiché et utilisé par `-t` |
| `difficulty` | 1, 2 ou 3 |
| `question` | l'énoncé |
| `code` | optionnel : bloc de code affiché sous l'énoncé |
| `options` | 2 à 16 propositions |
| `answer` | index de la bonne réponse (0 = première), ou liste d'index pour une question à plusieurs réponses |
| `explanation` | optionnel : affiché après la correction |

L'ordre des propositions est mélangé à chaque tirage, donc l'ordre d'écriture
dans le fichier n'a pas d'importance. Le fichier est validé au chargement : un
index de réponse hors limites ou un `id` en double est signalé avec précision.

### Reproduire le format du contrôle

Le QCM hebdomadaire a un format fixe : énoncés en anglais, 6 propositions,
**1 ou 2** bonnes réponses sans qu'on sache combien, et une seule case fausse
annule la question. Trois champs en tête du fichier reproduisent ces conditions :

```json
{
  "lesson": "Lesson 2",
  "exam_style": true,
  "max_answers": 2,
  "options_per_question": 6,
  "questions": [ ... ]
}
```

- `exam_style` : le QCM ne révèle jamais le nombre de bonnes réponses et accepte
  jusqu'à `max_answers` cases par question
- `options_per_question` : vérifié au chargement, pour qu'aucune question
  n'échappe au format

Sans ces champs, le comportement reste celui de la Lesson 1 : le nombre de
bonnes réponses attendues est affiché.

## Leçons

| Leçon | Contenu | Questions |
| :-- | :-- | --: |
| [Lesson 1](Lesson%201/) | Variables, types, opérateurs, conditions, boucles, listes, slicing, chaînes, dictionnaires, tuples, sets, matrices, fonctions, lambda, exceptions, fichiers | 91 |
| [Lesson 2](Lesson%202/) | Classes et objets, `__init__` et `self`, encapsulation, héritage, polymorphisme, composition, surcharge des opérateurs, `__repr__` | 66 |
| [Lesson 3](Lesson%203/) | pip, environnements virtuels, `venv`, conda, pipenv, poetry, reproductibilité | — |
| [Lesson 4](Lesson%204/) | Django : projet et applications, vues, URLs, modèles, migrations, shell et ORM, templates, paramètres GET, formulaires, admin | 68 |
| [Lesson 5](Lesson%205/) | FastAPI : routes, paramètres de chemin et de requête, Uvicorn, documentation `/docs`, REST et codes HTTP, SQLAlchemy, Pydantic, `Depends`, `response_model`, relation un-à-plusieurs | 75 |

Chaque leçon contient aussi une fiche de révision (`revision_*.tex`, à compiler
sur Overleaf) et, quand le cours en propose, un notebook d'exercices corrigés.
La [Lesson 3](Lesson%203/) contient en plus le compte-rendu des deux exercices
du cours, avec les commandes et les sorties obtenues. La
[Lesson 4](Lesson%204/) contient le projet Django complet (tutoriel et
exercices) : voir son README pour l'installer et le lancer. La
[Lesson 5](Lesson%205/) contient l'API FastAPI complète (tutoriel et
exercice sur les posts) avec ses 28 tests.

## Bonus

[bonus_moteur_3d/](bonus_moteur_3d/) — **CRYPTE**, un moteur 3D en lancer de
rayons qui tourne en temps réel dans le terminal, en Python pur et sans aucune
dépendance : labyrinthe, textures, sprites et export PNG sont tous générés par
le code.

```bash
cd bonus_moteur_3d
python crypte.py
```
