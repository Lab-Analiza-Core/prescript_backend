from django.conf import settings
from django.db import models
from django.db.models import Q


class Country(models.Model):
    interactive_core_id = models.PositiveIntegerField(unique=True, blank=True, null=True)
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=100, unique=True)
    currency = models.CharField(max_length=3, blank=True)
    phone_code = models.CharField(max_length=10, blank=True)
    dni_mask = models.CharField(max_length=50, blank=True)
    phone_mask = models.CharField(max_length=50, blank=True)
    timezone = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "countries"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class UserCountryAccess(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="prescript_country_accesses",
    )
    role_code = models.CharField(max_length=50)
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="user_accesses",
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=30, default="local")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_country_access"
        ordering = ["user_id", "role_code", "country__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role_code", "country"],
                name="user_role_country_unique",
            ),
            models.UniqueConstraint(
                fields=["user", "role_code"],
                condition=Q(country__isnull=True),
                name="user_global_role_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"], name="user_country_active_idx"),
            models.Index(fields=["country", "role_code"], name="country_role_idx"),
        ]

    def __str__(self):
        country_code = self.country.code if self.country_id else "GLOBAL"
        return f"{self.user} - {self.role_code} - {country_code}"
