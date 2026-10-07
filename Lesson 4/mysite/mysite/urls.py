"""Routes du projet.

Chaque application declare ses propres routes dans son urls.py ; le projet se
contente de les brancher sous un prefixe avec include().
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # la route polls/ utilise le fichier urls.py du dossier polls (d'ou polls.urls)
    path("polls/", include("polls.urls")),
    path("ynav/", include("ynav.urls")),
    path("admin/", admin.site.urls),
    # la racine du site renvoie vers le sommaire des exercices
    path("", RedirectView.as_view(pattern_name="ynav:home")),
]
