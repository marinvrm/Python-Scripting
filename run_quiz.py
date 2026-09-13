#!/usr/bin/env python3
"""Lanceur de QCM depuis la racine du depot.

    python run_quiz.py                      menu des lecons disponibles
    python run_quiz.py "Lesson 1"           QCM de la Lesson 1
    python run_quiz.py 1 -n 10              par numero, avec les options habituelles
    python run_quiz.py --lecons             liste les lecons puis quitte

Toutes les options du QCM (-n, -t, -d, --revision, ...) sont transmises telles
quelles. Voir `python run_quiz.py "Lesson 1" --help`.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from quiz.cli import main  # noqa: E402

BANK_NAME = "questions.json"


def find_lessons():
    """Les dossiers de lecon contenant une banque de questions, tries par nom."""
    return sorted(
        (path for path in ROOT.iterdir() if path.is_dir() and (path / BANK_NAME).is_file()),
        key=lambda path: path.name.lower(),
    )


def match_lesson(lessons, needle):
    """Retrouve une lecon par numero de menu, par nom exact ou par fragment."""
    if needle.isdigit():
        index = int(needle) - 1
        if 0 <= index < len(lessons):
            return lessons[index]

    needle = needle.lower()
    exact = [path for path in lessons if path.name.lower() == needle]
    if exact:
        return exact[0]

    partial = [path for path in lessons if needle in path.name.lower()]
    return partial[0] if len(partial) == 1 else None


def print_lessons(lessons):
    print("\nLecons disponibles :\n")
    for number, path in enumerate(lessons, start=1):
        print(f"  {number}. {path.name}")
    print()


def choose(lessons):
    """Menu interactif quand aucune lecon n'est passee en argument."""
    if len(lessons) == 1:
        return lessons[0]

    print_lessons(lessons)
    try:
        answer = input("Quelle lecon ? (numero, vide pour la derniere) > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not answer:
        return lessons[-1]

    lesson = match_lesson(lessons, answer)
    if lesson is None:
        print(f"Lecon inconnue : {answer}", file=sys.stderr)
    return lesson


def run(argv):
    lessons = find_lessons()
    if not lessons:
        print(f"Aucun dossier de lecon avec un fichier {BANK_NAME}.", file=sys.stderr)
        return 1

    if argv and argv[0] == "--lecons":
        print_lessons(lessons)
        return 0

    # Un premier argument qui n'est pas une option designe la lecon.
    if argv and not argv[0].startswith("-"):
        lesson = match_lesson(lessons, argv[0])
        if lesson is None:
            print(f"Lecon inconnue : {argv[0]}", file=sys.stderr)
            print_lessons(lessons)
            return 1
        rest = argv[1:]
    else:
        lesson = choose(lessons)
        if lesson is None:
            return 1
        rest = argv

    return main(lesson / BANK_NAME, rest)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
