from django.core.validators import MinValueValidator
from django.db import models


class Pakiman(models.Model):
    name = models.CharField(max_length=50)
    type = models.CharField(max_length=30)
    level = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    attack = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["-level", "name"]
        verbose_name_plural = "pakimans"

    def __str__(self):
        return f"{self.name} ({self.type}, level {self.level})"
