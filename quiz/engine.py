"""Moteur de QCM : chargement des banques de questions, tirage et correction.

Une banque est un fichier `questions.json` place dans le dossier d'une lecon.
Le moteur ne fait aucun affichage : il se contente de charger, valider, tirer
et corriger. L'affichage est dans `quiz.cli`.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

LETTERS = "abcdefghijklmnop"


class QuizError(Exception):
    """Banque de questions introuvable ou mal formee."""


@dataclass(frozen=True)
class Question:
    """Une question telle qu'elle est ecrite dans le fichier JSON."""

    id: str
    topic: str
    difficulty: int
    prompt: str
    options: tuple
    answers: frozenset
    explanation: str = ""
    code: str = ""

    @property
    def is_multiple(self) -> bool:
        """Vrai si plusieurs bonnes reponses sont attendues."""
        return len(self.answers) > 1


@dataclass(frozen=True)
class AskedQuestion:
    """Une question prete a etre posee : options melangees, indices recalcules.

    En mode examen, `max_select` borne le nombre de cases cochables et le
    nombre exact de bonnes reponses n'est jamais devoile.
    """

    question: Question
    options: tuple
    answers: frozenset
    exam_style: bool = False
    max_select: int = 0  # 0 = pas de limite

    @property
    def is_multiple(self) -> bool:
        return len(self.answers) > 1

    def is_correct(self, selection) -> bool:
        return frozenset(selection) == self.answers

    def correct_letters(self) -> str:
        return ", ".join(LETTERS[i] for i in sorted(self.answers))


@dataclass
class Bank:
    """L'ensemble des questions d'une lecon.

    `exam_style` reproduit les conditions du controle : toutes les questions
    ont le meme nombre de propositions, de 1 a `max_answers` sont correctes,
    et l'enonce ne dit jamais combien. Une seule case fausse annule la question.
    """

    lesson: str
    title: str
    questions: list
    path: Path = None
    exam_style: bool = False
    max_answers: int = 2
    options_per_question: int = 0  # 0 = pas de contrainte

    def topics(self) -> list:
        """Les themes presents, dans l'ordre de premiere apparition."""
        seen = []
        for question in self.questions:
            if question.topic not in seen:
                seen.append(question.topic)
        return seen

    def count_by_topic(self) -> dict:
        counts = {}
        for question in self.questions:
            counts[question.topic] = counts.get(question.topic, 0) + 1
        return counts


def load_bank(path) -> Bank:
    """Charge et valide une banque de questions JSON."""
    path = Path(path)
    if not path.is_file():
        raise QuizError(f"Banque de questions introuvable : {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise QuizError(f"JSON invalide dans {path.name} : {error}") from error

    if not isinstance(raw, dict) or "questions" not in raw:
        raise QuizError(f"{path.name} doit contenir un objet avec une cle 'questions'.")

    questions = [_parse_question(item, index) for index, item in enumerate(raw["questions"])]
    if not questions:
        raise QuizError(f"{path.name} ne contient aucune question.")

    _check_unique_ids(questions, path)

    bank = Bank(
        lesson=raw.get("lesson", path.parent.name),
        title=raw.get("title", ""),
        questions=questions,
        path=path,
        exam_style=bool(raw.get("exam_style", False)),
        max_answers=int(raw.get("max_answers", 2)),
        options_per_question=int(raw.get("options_per_question", 0)),
    )
    _check_exam_format(bank, path)
    return bank


def _parse_question(item, index: int) -> Question:
    """Transforme un dict JSON en Question, en verifiant le contenu."""
    where = item.get("id") or f"question #{index + 1}"

    for field in ("question", "options", "answer"):
        if field not in item:
            raise QuizError(f"{where} : champ obligatoire '{field}' manquant.")

    options = item["options"]
    if not isinstance(options, list) or len(options) < 2:
        raise QuizError(f"{where} : 'options' doit etre une liste d'au moins 2 elements.")
    if len(options) > len(LETTERS):
        raise QuizError(f"{where} : {len(options)} options, maximum {len(LETTERS)}.")

    answer = item["answer"]
    indices = answer if isinstance(answer, list) else [answer]
    if not indices:
        raise QuizError(f"{where} : 'answer' ne peut pas etre vide.")
    for position in indices:
        if not isinstance(position, int) or not 0 <= position < len(options):
            raise QuizError(
                f"{where} : 'answer' = {position} hors des options (0 a {len(options) - 1})."
            )

    return Question(
        id=item.get("id", f"q{index + 1:03d}"),
        topic=item.get("topic", "Divers"),
        difficulty=int(item.get("difficulty", 1)),
        prompt=item["question"],
        options=tuple(str(option) for option in options),
        answers=frozenset(indices),
        explanation=item.get("explanation", ""),
        code=item.get("code", "") or "",
    )


def _check_unique_ids(questions, path) -> None:
    seen = set()
    for question in questions:
        if question.id in seen:
            raise QuizError(f"{path.name} : identifiant duplique '{question.id}'.")
        seen.add(question.id)


def _check_exam_format(bank: Bank, path) -> None:
    """Verifie que la banque respecte le format annonce (nb d'options, nb de reponses)."""
    for question in bank.questions:
        if bank.options_per_question and len(question.options) != bank.options_per_question:
            raise QuizError(
                f"{path.name} : {question.id} a {len(question.options)} propositions, "
                f"{bank.options_per_question} attendues."
            )
        if bank.exam_style and len(question.answers) > bank.max_answers:
            raise QuizError(
                f"{path.name} : {question.id} a {len(question.answers)} bonnes reponses, "
                f"maximum {bank.max_answers}."
            )


def select(bank: Bank, count: int, topics=None, difficulties=None, rng=None) -> list:
    """Tire `count` questions au hasard, filtrees par theme et/ou difficulte."""
    rng = rng or random.Random()
    pool = list(bank.questions)

    if topics:
        wanted = [topic.lower() for topic in topics]
        pool = [q for q in pool if any(w in q.topic.lower() for w in wanted)]
    if difficulties:
        pool = [q for q in pool if q.difficulty in difficulties]

    if not pool:
        raise QuizError("Aucune question ne correspond aux filtres demandes.")

    rng.shuffle(pool)
    return pool[:count]


def prepare(question: Question, rng=None, shuffle: bool = True, bank: Bank = None) -> AskedQuestion:
    """Melange les options d'une question et recalcule les indices corrects."""
    order = list(range(len(question.options)))
    if shuffle:
        rng = rng or random.Random()
        rng.shuffle(order)

    options = tuple(question.options[i] for i in order)
    answers = frozenset(
        new_index for new_index, old_index in enumerate(order) if old_index in question.answers
    )
    return AskedQuestion(
        question=question,
        options=options,
        answers=answers,
        exam_style=bool(bank and bank.exam_style),
        max_select=bank.max_answers if bank and bank.exam_style else 0,
    )


def parse_selection(text: str, option_count: int) -> frozenset:
    """Lit une reponse saisie ("a", "b,c", "1 3") et renvoie les indices choisis.

    Leve ValueError si la saisie ne designe pas des options valides.
    """
    tokens = [token for token in text.replace(",", " ").replace(";", " ").split() if token]
    if not tokens:
        raise ValueError("Reponse vide.")

    indices = set()
    for token in tokens:
        token = token.strip().lower().rstrip(")").rstrip(".")
        if token.isdigit():
            index = int(token) - 1
        elif len(token) == 1 and token in LETTERS:
            index = LETTERS.index(token)
        else:
            raise ValueError(f"'{token}' n'est pas une option.")
        if not 0 <= index < option_count:
            raise ValueError(f"'{token}' est en dehors des options proposees.")
        indices.add(index)

    return frozenset(indices)


def score_by_topic(results) -> dict:
    """Agrege les resultats par theme : {theme: (reussies, posees)}."""
    stats = {}
    for asked, correct in results:
        good, total = stats.get(asked.question.topic, (0, 0))
        stats[asked.question.topic] = (good + bool(correct), total + 1)
    return stats
