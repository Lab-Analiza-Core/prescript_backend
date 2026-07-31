from django.db import models


class MedicineCatalogMirror(models.Model):
    interactive_core_product_id = models.PositiveIntegerField(unique=True)
    code = models.CharField(max_length=50, unique=True, blank=True, null=True)
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

    def __str__(self):
        return self.name


class ExamCatalogMirror(models.Model):
    interactive_core_exam_id = models.PositiveIntegerField(unique=True)
    interactive_core_product_id = models.PositiveIntegerField(blank=True, null=True)
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

    def __str__(self):
        return self.name
