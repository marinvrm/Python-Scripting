from django.http import HttpResponse
from django.shortcuts import render
from django.utils.html import escape

from .models import Question


def index(request):
    """Version du cours : le HTML est construit a la main dans le code.

    escape() est indispensable ici : un texte de question contenant du HTML
    serait sinon injecte tel quel dans la page. Les templates, eux, echappent
    automatiquement les variables, c'est une raison de plus de les preferer.
    """
    content = "<h1>Questions</h1>"
    content += "<ul>"
    for question in Question.objects.all():
        content += "<li>"
        content += (
            f"{escape(question.question_text)} - {question.pub_date}. "
            f"{question.choice_set.count()} choices"
        )
        content += "<ul>"
        str_choices = [
            f"<li>{escape(c.choice_text)} / {c.votes}</li>"
            for c in question.choice_set.all()
        ]
        content += "".join(str_choices)
        content += "</ul>"
        content += "</li>"
    content += "</ul>"
    return HttpResponse(content)


def hello(request):
    """Exercice : http://localhost:8000/polls/hello affiche Hello World en h1."""
    return HttpResponse("<h1>Hello World</h1>")


def showQuestionsWithTemplate(request):
    """Meme contenu que index(), mais l'affichage est delegue au template."""
    context = {"questions": Question.objects.all()}
    return render(request, "polls/questions.html", context)
