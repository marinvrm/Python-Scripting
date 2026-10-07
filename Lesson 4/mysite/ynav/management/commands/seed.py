"""Remplit la base avec quelques donnees de demonstration.

    python manage.py seed

Sans effet sur une table qui contient deja des lignes : la commande peut etre
relancee sans creer de doublons.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from polls.models import Question
from ynav.models import Pakiman

PAKIMANS = [
    ("Pikachu", "Electric", 12, 55),
    ("Bulbasaur", "Grass", 5, 49),
    ("Charmander", "Fire", 8, 52),
    ("Squirtle", "Water", 3, 48),
    ("Mewtwo", "Psychic", 70, 110),
]

QUESTIONS = {
    "What's up?": [("Not much", 2), ("The sky", 5)],
    "Favourite Python web framework?": [("Django", 7), ("Flask", 4), ("FastAPI", 6)],
}


class Command(BaseCommand):
    help = "Ajoute des Pakiman et des questions de demonstration."

    def handle(self, *args, **options):
        if Pakiman.objects.exists():
            self.stdout.write("Pakiman : table deja remplie, rien a faire.")
        else:
            Pakiman.objects.bulk_create(
                Pakiman(name=n, type=t, level=lv, attack=a) for n, t, lv, a in PAKIMANS
            )
            self.stdout.write(self.style.SUCCESS(f"{len(PAKIMANS)} Pakiman ajoutes."))

        if Question.objects.exists():
            self.stdout.write("Questions : table deja remplie, rien a faire.")
        else:
            for text, choices in QUESTIONS.items():
                q = Question.objects.create(question_text=text, pub_date=timezone.now())
                for choice_text, votes in choices:
                    q.choice_set.create(choice_text=choice_text, votes=votes)
            self.stdout.write(self.style.SUCCESS(f"{len(QUESTIONS)} questions ajoutees."))
