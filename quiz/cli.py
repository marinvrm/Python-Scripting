"""Interface terminale du QCM : pose les questions, corrige, affiche le bilan."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path

from .engine import (
    LETTERS,
    QuizError,
    load_bank,
    parse_selection,
    prepare,
    score_by_topic,
    select,
)

HISTORY_FILE = ".quiz_history.json"
QUIT_WORDS = {"q", "quit", "exit", "stop"}
SKIP_WORDS = {"s", "skip", "passer"}
WIDTH = 72


# --------------------------------------------------------------------------
# Couleurs
# --------------------------------------------------------------------------

def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:  # active les sequences ANSI sur les consoles Windows
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            return False
    return True


class Style:
    """Petites aides de couleur, neutralisees si le terminal ne suit pas."""

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, text, code):
        return f"\033[{code}m{text}\033[0m" if self.enabled else str(text)

    def bold(self, text):
        return self._wrap(text, "1")

    def dim(self, text):
        return self._wrap(text, "2")

    def green(self, text):
        return self._wrap(text, "32")

    def red(self, text):
        return self._wrap(text, "31")

    def yellow(self, text):
        return self._wrap(text, "33")

    def cyan(self, text):
        return self._wrap(text, "36")


# --------------------------------------------------------------------------
# Historique (pour le mode revision)
# --------------------------------------------------------------------------

def _history_path(bank_path: Path) -> Path:
    return bank_path.parent / HISTORY_FILE


def load_history(bank_path: Path) -> dict:
    path = _history_path(bank_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_history(bank_path: Path, history: dict) -> None:
    try:
        _history_path(bank_path).write_text(
            json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass  # l'historique est un confort, jamais un blocage


def update_history(history: dict, results) -> dict:
    for asked, correct in results:
        entry = history.get(asked.question.id, {"asked": 0, "wrong": 0})
        entry["asked"] = entry.get("asked", 0) + 1
        if not correct:
            entry["wrong"] = entry.get("wrong", 0) + 1
        entry["last_wrong"] = not correct
        entry["last_seen"] = datetime.now().isoformat(timespec="seconds")
        history[asked.question.id] = entry
    return history


# --------------------------------------------------------------------------
# Affichage
# --------------------------------------------------------------------------

def _print_header(style: Style, bank, total: int) -> None:
    title = bank.title or bank.lesson
    print()
    print(style.cyan("=" * WIDTH))
    header = f" QCM - {bank.lesson}"
    if title != bank.lesson:
        header += f" - {title}"
    print(style.bold(header))
    plural = "s" if total > 1 else ""
    print(f" {total} question{plural}  |  q = quitter, s = passer la question")
    print(style.cyan("=" * WIDTH))


def _print_question(style: Style, asked, number: int, total: int) -> None:
    question = asked.question
    dots = "*" * question.difficulty + "." * (3 - question.difficulty)
    print()
    print(style.dim("-" * WIDTH))
    left = f" Question {number}/{total}"
    right = f"{question.topic} [{dots}] "
    padding = max(1, WIDTH - len(left) - len(right))
    print(style.bold(left) + " " * padding + style.dim(right))
    print(style.dim("-" * WIDTH))
    print()
    print(question.prompt)

    if question.code:
        print()
        for line in question.code.splitlines():
            print(style.cyan("    " + line))

    print()
    for index, option in enumerate(asked.options):
        print("  " + style.bold(LETTERS[index]) + ") " + option)

    if asked.is_multiple:
        print()
        print(style.yellow(
            f"  Plusieurs bonnes reponses ({len(asked.answers)}) - exemple : a,c"
        ))


def _ask(style: Style, asked):
    """Lit la saisie de l'utilisateur. Renvoie un frozenset, 'skip' ou 'quit'."""
    last_letter = LETTERS[len(asked.options) - 1]
    while True:
        try:
            raw = input("\n  Votre reponse > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return "quit"

        if not raw:
            continue
        if raw.lower() in QUIT_WORDS:
            return "quit"
        if raw.lower() in SKIP_WORDS:
            return "skip"

        try:
            selection = parse_selection(raw, len(asked.options))
        except ValueError as error:
            print(style.red(f"  {error} Attendu : une lettre de a a {last_letter}."))
            continue

        if not asked.is_multiple and len(selection) > 1:
            print(style.red("  Cette question n'attend qu'une seule reponse."))
            continue
        return selection


def _print_verdict(style: Style, asked, selection, correct: bool) -> None:
    print()
    if correct:
        print(style.green("  [OK] Bonne reponse."))
    elif selection is None:
        print(style.yellow(f"  [--] Passee. Reponse : {asked.correct_letters()}"))
    else:
        print(style.red(f"  [X] Faux. Bonne reponse : {asked.correct_letters()}"))
        for index in sorted(asked.answers):
            print(style.dim(f"       {LETTERS[index]}) {asked.options[index]}"))

    if asked.question.explanation:
        print(style.dim("       " + asked.question.explanation))


def _bar(ratio: float, width: int = 30) -> str:
    filled = round(ratio * width)
    return "#" * filled + "." * (width - filled)


def _print_report(style: Style, results) -> None:
    if not results:
        print("\nAucune question repondue.")
        return

    good = sum(1 for _, correct in results if correct)
    total = len(results)
    ratio = good / total
    percent = round(ratio * 100)

    if percent >= 70:
        color = style.green
    elif percent >= 50:
        color = style.yellow
    else:
        color = style.red

    print()
    print(style.cyan("=" * WIDTH))
    print(style.bold(" Resultat"))
    print(style.cyan("=" * WIDTH))
    print()
    print("  " + color(_bar(ratio)) + "  " + color(style.bold(f"{good}/{total}"))
          + f"  ({percent} %)")

    print()
    print(style.bold("  Par theme"))
    for topic, (topic_good, topic_total) in sorted(score_by_topic(results).items()):
        mark = style.green("ok") if topic_good == topic_total else style.red("--")
        print(f"    {mark}  {topic:<34} {topic_good}/{topic_total}")

    missed = [asked for asked, correct in results if not correct]
    if missed:
        print()
        print(style.bold("  A revoir"))
        for asked in missed:
            prompt = asked.question.prompt.splitlines()[0]
            if len(prompt) > WIDTH - 10:
                prompt = prompt[: WIDTH - 13] + "..."
            print("    - " + prompt)
        print()
        print(style.dim("  Rejouer uniquement ces questions : python quiz.py --revision"))
    else:
        print()
        print(style.green("  Sans faute."))
    print()


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------

def run_session(style: Style, bank, questions, rng, shuffle_options: bool):
    """Pose les questions une a une, renvoie la liste (AskedQuestion, correct)."""
    results = []
    total = len(questions)

    _print_header(style, bank, total)

    for number, question in enumerate(questions, start=1):
        asked = prepare(question, rng=rng, shuffle=shuffle_options)
        _print_question(style, asked, number, total)

        answer = _ask(style, asked)
        if answer == "quit":
            print(style.yellow("\n  Session interrompue."))
            break
        if answer == "skip":
            _print_verdict(style, asked, None, correct=False)
            results.append((asked, False))
            continue

        correct = asked.is_correct(answer)
        _print_verdict(style, asked, answer, correct)
        results.append((asked, correct))

    return results


def build_parser(default_count: int) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="QCM interactif de revision.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python quiz.py                     20 questions au hasard\n"
            "  python quiz.py -n 10               10 questions\n"
            "  python quiz.py -t listes -t dict   seulement certains themes\n"
            "  python quiz.py -d 3                seulement les questions difficiles\n"
            "  python quiz.py --revision          rejoue les questions ratees\n"
            "  python quiz.py --themes            liste les themes disponibles\n"
        ),
    )
    parser.add_argument("-n", "--nombre", type=int, default=default_count,
                        help=f"nombre de questions (defaut : {default_count})")
    parser.add_argument("-t", "--theme", action="append", default=None,
                        help="filtre par theme (repetable, recherche partielle)")
    parser.add_argument("-d", "--difficulte", action="append", type=int, choices=[1, 2, 3],
                        default=None, help="filtre par difficulte (repetable)")
    parser.add_argument("--revision", action="store_true",
                        help="ne rejoue que les questions ratees la derniere fois")
    parser.add_argument("--themes", action="store_true",
                        help="affiche les themes de la banque puis quitte")
    parser.add_argument("--ordre-fixe", action="store_true",
                        help="ne melange pas l'ordre des reponses")
    parser.add_argument("--seed", type=int, default=None,
                        help="graine aleatoire, pour rejouer le meme tirage")
    return parser


def main(bank_path, argv=None, default_count: int = 20) -> int:
    """Point d'entree : `python quiz.py [options]` dans un dossier de lecon."""
    args = build_parser(default_count).parse_args(argv if argv is not None else sys.argv[1:])

    # Les questions sont accentuees. Sur une vraie console, Python ecrit deja en
    # Unicode ; quand la sortie est redirigee vers un fichier ou un tube, elle
    # tombe sur l'encodage local, qui peut ne pas suffire.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    style = Style(_supports_color())

    try:
        bank = load_bank(bank_path)
    except QuizError as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1

    if args.themes:
        print()
        print(style.bold(f"{bank.lesson} - {len(bank.questions)} questions"))
        print()
        for topic, count in sorted(bank.count_by_topic().items()):
            print(f"  {topic:<38} {count:>3}")
        print()
        return 0

    history = load_history(bank.path)
    rng = random.Random(args.seed)

    if args.revision:
        to_review = {qid for qid, entry in history.items() if entry.get("last_wrong")}
        questions = [q for q in bank.questions if q.id in to_review]
        if not questions:
            print(style.green(
                "\n  Aucune question ratee en memoire. Lance un QCM : python quiz.py\n"
            ))
            return 0
        rng.shuffle(questions)
        questions = questions[: max(1, args.nombre)]
        print(style.yellow(f"\n  Mode revision : {len(questions)} question(s) ratee(s)."))
    else:
        try:
            questions = select(
                bank,
                count=max(1, args.nombre),
                topics=args.theme,
                difficulties=args.difficulte,
                rng=rng,
            )
        except QuizError as error:
            print(f"Erreur : {error}", file=sys.stderr)
            print("Themes disponibles : " + ", ".join(bank.topics()), file=sys.stderr)
            return 1

    results = run_session(style, bank, questions, rng, shuffle_options=not args.ordre_fixe)
    _print_report(style, results)

    if results:
        save_history(bank.path, update_history(history, results))

    return 0
