from django import forms

from .models import Pakiman


class NameForm(forms.Form):
    """Formulaire simple : un seul champ, aucune table derriere."""

    name = forms.CharField(label="Name", max_length=100)


class PakimanForm(forms.ModelForm):
    """Formulaire genere a partir du modele : champs et validation inclus."""

    class Meta:
        model = Pakiman
        fields = ["name", "type", "level", "attack"]
