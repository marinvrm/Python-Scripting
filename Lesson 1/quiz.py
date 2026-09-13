#!/usr/bin/env python3
"""QCM interactif de la Lesson 1.

A lancer depuis ce dossier :

    python quiz.py                  20 questions au hasard
    python quiz.py -n 10            10 questions
    python quiz.py -t listes        seulement le theme "Listes"
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
