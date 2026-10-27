from django.db import models


class MedicineCatalogMirror(models.Model):
    interactive_core_product_id = models.PositiveIntegerField()
    country = models.ForeignKey(
        "Country",
        on_delete=models.PROTECT,
        related_name="medicine_catalog",
    )
    code = models.CharField(max_length=50, blank=True, null=True)
    name = models.CharField(max_length=255)
    presentation = models.CharField(max_length=255, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    active_ingredient = models.CharField(max_length=255, blank=True, null=True)
    commercial_house = models.CharField(max_length=255, blank=True, null=True)
    specialty_ids = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "medicine_catalog_mirror"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["country", "interactive_core_product_id"],
                name="med_country_product_uniq",
            ),
            models.UniqueConstraint(
                fields=["country", "code"],
                condition=models.Q(code__isnull=False),
                name="medicine_country_code_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["country", "is_active", "name"], name="medicine_country_active_idx"),
        ]

    def __str__(self):
        return self.name


class DoctorMedicine(models.Model):
    """Catalogo propio de un medico que no usa el catalogo sincronizado de Interactive Core."""

    CATEGORY_CHOICES = [
        ("favorite", "Favorito"),
        ("complementary", "Complementario"),
        ("undetermined", "Indeterminado"),
    ]

    doctor = models.ForeignKey(
        "DoctorPortalProfile",
        on_delete=models.CASCADE,
        related_name="own_medicines",
    )
    name = models.CharField(max_length=255)
    presentation = models.CharField(max_length=255, blank=True, default="")
    active_ingredient = models.CharField(max_length=255, blank=True, default="")
    commercial_house = models.CharField(max_length=255, blank=True, default="")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="undetermined")
    # Valores que el editor de recetas precarga al elegir el medicamento.
    default_dosage = models.CharField(max_length=120, blank=True, default="")
    default_frequency = models.CharField(max_length=120, blank=True, default="")
    default_duration = models.CharField(max_length=120, blank=True, default="")
    default_instructions = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "doctor_medicines"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "name", "presentation"],
                name="doctor_medicine_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["doctor", "is_active", "name"], name="doctor_medicine_active_idx"),
        ]

    def __str__(self):
        return self.name


class ExamCatalogMirror(models.Model):
    interactive_core_exam_id = models.PositiveIntegerField()
    interactive_core_product_id = models.PositiveIntegerField(blank=True, null=True)
    country = models.ForeignKey(
        "Country",
        on_delete=models.PROTECT,
        related_name="exam_catalog",
    )
    code = models.CharField(max_length=50, blank=True, null=True)
    name = models.CharField(max_length=255)
    area = models.CharField(max_length=120, blank=True, null=True)
    sample_type = models.CharField(max_length=120, blank=True, null=True)
    specialty_ids = models.JSONField(default=list, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "exam_catalog_mirror"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["country", "is_active", "name"], name="exam_country_active_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["country", "interactive_core_exam_id"],
                name="exam_country_product_unique",
            ),
        ]

    def __str__(self):
        return self.name
