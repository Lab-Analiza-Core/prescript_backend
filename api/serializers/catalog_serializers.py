from rest_framework import serializers

from api.models import ExamCatalogMirror, MedicineCatalogMirror


class MedicineCatalogMirrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicineCatalogMirror
        fields = [
            "id",
            "interactive_core_product_id",
            "code",
            "name",
            "presentation",
            "category",
            "active_ingredient",
            "commercial_house",
            "specialty_ids",
            "metadata",
            "is_active",
            "last_synced_at",
        ]


class ExamCatalogMirrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamCatalogMirror
        fields = [
            "id",
            "interactive_core_exam_id",
            "interactive_core_product_id",
            "code",
            "name",
            "area",
            "sample_type",
            "specialty_ids",
            "price",
            "metadata",
            "is_active",
            "last_synced_at",
        ]
