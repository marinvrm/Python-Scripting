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

## Leçons

| Leçon | Contenu | Questions |
| :-- | :-- | --: |
| [Lesson 1](Lesson%201/) | Variables, types, opérateurs, conditions, boucles, listes, slicing, chaînes, dictionnaires, tuples, sets, matrices, fonctions, lambda, exceptions, fichiers | 91 |
