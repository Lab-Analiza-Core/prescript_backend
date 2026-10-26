from django.conf import settings
from django.db import models

from .organization_models import Organization


class ThemeSetting(models.Model):
    """Apariencia personalizada: una fila global (organization nula) y una por organizacion.

    `colors` guarda solo las claves que se sobrescriben; el resto se hereda
    (organizacion -> global -> colores de fabrica).
    """

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="theme",
        blank=True,
        null=True,
    )
    colors = models.JSONField(default=dict, blank=True)
    font = models.CharField(max_length=40, blank=True, default="")
    # Logo como data URL (png/jpeg/webp/svg validado): evita depender de almacenamiento de archivos.
    logo = models.TextField(blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "theme_settings"
        constraints = [
            # Una sola fila global (OneToOne no basta: NULL se repite).
            models.UniqueConstraint(
                models.Value(1),
                condition=models.Q(organization__isnull=True),
                name="theme_single_global_row",
            ),
        ]

    def __str__(self):
        return f"Tema de {self.organization or 'sistema'}"

    @property
    def is_empty(self):
        return not (self.colors or self.font or self.logo)
