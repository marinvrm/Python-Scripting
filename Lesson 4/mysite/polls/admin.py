from django.contrib import admin

from .models import Choice, Question

# Rend les deux tables editables depuis /admin
admin.site.register([Question, Choice])
