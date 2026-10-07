"""Template tag personnalise : ajoute une classe CSS au widget d'un champ.

Django genere lui-meme le <input> d'un champ de formulaire ; ce filtre permet
d'y glisser les classes Bulma sans reecrire le HTML a la main :

    {% load bulma %}
    {{ form.name|add_class:"input" }}
"""
from django import template

register = template.Library()


@register.filter
def add_class(field, css_class):
    return field.as_widget(attrs={"class": css_class})
