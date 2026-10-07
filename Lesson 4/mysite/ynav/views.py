import datetime

from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponse
from django.shortcuts import redirect, render

from .forms import NameForm, PakimanForm
from .models import Pakiman

# Garde-fou pour /query/range : sans limite, ?min=0&max=100000000 genererait
# une page de plusieurs Go.
MAX_RANGE_SIZE = 1000


def parse_int(value):
    """Convertit un parametre de requete en entier, ou None s'il est absent ou invalide."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def home(request):
    """Sommaire : un lien vers chaque exercice."""
    return render(request, "ynav/home.html")


# ---------------------------------------------------------------- HttpResponse


def hello(request):
    return HttpResponse("<h1>Hello World</h1>")


def profile(request):
    # Les triples guillemets permettent d'ecrire un texte sur plusieurs lignes
    return HttpResponse("""<html>
    <head>
        <title>Profile</title>
    </head>
    <body>
        <h1>Profile</h1>
        <p>First Name: John</p>
        <p>Last Name: Doe</p>
    </body>
</html>""")


def server_time(request):
    # Heure de la machine qui execute le serveur, pas celle du navigateur
    t = f"It is {datetime.datetime.now().strftime('%H:%M')}"
    return HttpResponse(f"<h1>{t}</h1>")


# ---------------------------------------------------------------- templates + parametres GET


def query(request):
    # .get() renvoie None si le parametre est absent, la ou ["p"] leverait une erreur
    p = request.GET.get("p")
    return render(request, "ynav/query.html", {"p": p})


def query_profile(request):
    context = {
        "first_name": request.GET.get("first_name", ""),
        "last_name": request.GET.get("last_name", ""),
    }
    return render(request, "ynav/query_profile.html", context)


def query_range(request):
    low = parse_int(request.GET.get("min"))
    high = parse_int(request.GET.get("max"))
    error = None
    numbers = []

    if low is None or high is None:
        error = "Give two integers: ?min=1&max=5"
    elif high - low + 1 > MAX_RANGE_SIZE:
        error = f"Range too large: at most {MAX_RANGE_SIZE} numbers."
    else:
        # range() exclut sa borne de fin, d'ou le + 1 pour inclure max
        numbers = list(range(low, high + 1))

    context = {"low": low, "high": high, "numbers": numbers, "error": error}
    return render(request, "ynav/range.html", context)


def multiplication(request):
    n = parse_int(request.GET.get("n"))
    rows = []
    if n is not None:
        rows = [(i, n * i) for i in range(1, 11)]
    return render(request, "ynav/multiplication.html", {"n": n, "rows": rows})


# ---------------------------------------------------------------- formulaires


def name_form(request):
    name = None
    if request.method == "POST":
        # Formulaire lie aux donnees envoyees : is_valid() lance la validation
        form = NameForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data["name"]
    else:
        # Premier affichage : formulaire vide
        form = NameForm()
    return render(request, "ynav/form.html", {"form": form, "name": name})


# ---------------------------------------------------------------- Pakiman (base de donnees)


def pakiman_list(request):
    """Tous les Pakiman, ou seulement ceux dont le niveau depasse ?level=N."""
    pakimans = Pakiman.objects.all()
    level = parse_int(request.GET.get("level"))
    invalid_level = "level" in request.GET and level is None
    if level is not None:
        # __gt = "greater than" : strictement superieur
        pakimans = pakimans.filter(level__gt=level)
    context = {"pakimans": pakimans, "level": level, "invalid_level": invalid_level}
    return render(request, "ynav/pakiman_list.html", context)


def pakiman_add(request):
    if request.method == "POST":
        form = PakimanForm(request.POST)
        if form.is_valid():
            form.save()
            # Redirection apres un POST reussi : un rafraichissement de la page
            # ne renverra pas le formulaire une seconde fois.
            return redirect("ynav:pakiman_list")
    else:
        form = PakimanForm()
    return render(request, "ynav/pakiman_add.html", {"form": form})


# ---------------------------------------------------------------- bonus : comptes


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("ynav:home")
    else:
        form = UserCreationForm()
    return render(request, "ynav/signup.html", {"form": form})
