#!/usr/bin/env python3
"""Cree le dossier d'une nouvelle lecon, pret a recevoir ses notebooks.

    python nouvelle_lecon.py "Lesson 2"
    python nouvelle_lecon.py "Lesson 2" --titre "Programmation orientee objet"

Le dossier recoit un quiz.py et un questions.json de depart, avec une question
d'exemple a remplacer.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

LAUNCHER = '''#!/usr/bin/env python3
"""QCM interactif de la {name}.

A lancer depuis ce dossier :

    python quiz.py                  20 questions au hasard
    python quiz.py -n 10            10 questions
    python quiz.py --revision       rejoue les questions ratees
    python quiz.py --help           toutes les options
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Le moteur est partage par toutes les lecons : il vit a la racine du depot.
# On place la racine en tete du chemin d'import pour que "quiz" designe bien le
# paquet quiz/ et non ce fichier.
sys.path.insert(0, str(HERE.parent))

from quiz.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(HERE / "questions.json"))
'''


def starter_bank(name, title):
    return {
        "lesson": name,
        "title": title,
        "questions": [
            {
                "id": "exemple-01",
                "topic": "A remplir",
                "difficulty": 1,
                "question": "Remplace cette question par les notions du cours.",
                "code": "print(\"Le champ code est optionnel\")",
                "options": [
                    "La bonne reponse",
                    "Une mauvaise reponse",
                    "Une autre mauvaise reponse",
                ],
                "answer": 0,
                "explanation": "Le champ explanation est affiche apres la correction.",
            }
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cree le dossier d'une nouvelle lecon.")
    parser.add_argument("nom", help='nom du dossier, par exemple "Lesson 2"')
    parser.add_argument("--titre", default="", help="sous-titre de la lecon")
    args = parser.parse_args(argv)

    folder = ROOT / args.nom
    if folder.exists():
        print(f"Le dossier existe deja : {folder.name}", file=sys.stderr)
        return 1

    folder.mkdir()
    (folder / "quiz.py").write_text(LAUNCHER.format(name=args.nom), encoding="utf-8")
    (folder / "questions.json").write_text(
        json.dumps(starter_bank(args.nom, args.titre), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Dossier cree : {args.nom}")
    print("  quiz.py")
    print("  questions.json   <- ecris les questions ici")
    print(f'\nDepose les notebooks du cours dans le dossier, puis : python run_quiz.py "{args.nom}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
