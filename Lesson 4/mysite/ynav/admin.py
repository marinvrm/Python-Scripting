from django.contrib import admin

from .models import Pakiman


@admin.register(Pakiman)
class PakimanAdmin(admin.ModelAdmin):
    list_display = ["name", "type", "level", "attack"]
    list_filter = ["type"]
    search_fields = ["name"]
