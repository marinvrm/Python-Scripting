from django.urls import path

from . import views

# Espace de noms : on ecrit {% url 'polls:index' %} sans risquer de collision
# avec une route du meme nom dans une autre application.
app_name = "polls"

urlpatterns = [
    path("", views.index, name="index"),
    path("hello", views.hello, name="hello"),
    path("questions", views.showQuestionsWithTemplate, name="questions"),
]
