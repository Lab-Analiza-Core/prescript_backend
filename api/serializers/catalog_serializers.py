from rest_framework import serializers

from api.models import DoctorMedicine, ExamCatalogMirror, MedicineCatalogMirror
from api.serializers.country_serializers import CountrySerializer


class MedicineCatalogMirrorSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)

    class Meta:
        model = MedicineCatalogMirror
        fields = [
            "id",
            "interactive_core_product_id",
            "country",
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
    country = CountrySerializer(read_only=True)

    class Meta:
        model = ExamCatalogMirror
        fields = [
            "id",
            "interactive_core_exam_id",
            "interactive_core_product_id",
            "country",
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


class DoctorMedicineSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorMedicine
        fields = [
            "id",
            "name",
            "presentation",
            "active_ingredient",
            "commercial_house",
            "category",
            "default_dosage",
            "default_frequency",
            "default_duration",
            "default_instructions",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Indique el nombre del medicamento.")
        return value

    def validate(self, attrs):
        name = attrs.get("name", getattr(self.instance, "name", ""))
        presentation = (attrs.get("presentation", getattr(self.instance, "presentation", "")) or "").strip()
        attrs["presentation"] = presentation
        doctor = getattr(getattr(self.context.get("request"), "user", None), "doctor_portal_profile", None)
        duplicates = DoctorMedicine.objects.filter(
            doctor=doctor, name__iexact=name, presentation__iexact=presentation
        )
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if doctor and duplicates.exists():
            raise serializers.ValidationError({"name": "Ya tiene un medicamento con ese nombre y presentacion."})
        return attrs


class SyncedCatalogEntrySerializer(serializers.Serializer):
    """Medicamento sincronizado visto por un medico: usa los campos anotados con su preferencia."""

    def to_representation(self, medicine):
        return {
            "source": "catalog",
            "id": medicine.id,
            "medicine": medicine.id,
            "doctor_medicine": None,
            "preference_id": medicine.preference_id,
            "name": medicine.name,
            "presentation": medicine.presentation or "",
            "active_ingredient": medicine.active_ingredient or "",
            "commercial_house": medicine.commercial_house or "",
            "category": medicine.effective_category,
            "notes": medicine.preference_notes or "",
            "default_dosage": "",
            "default_frequency": "",
            "default_duration": "",
            "default_instructions": "",
            "is_active": medicine.is_active,
        }


class OwnCatalogEntrySerializer(serializers.Serializer):
    """Medicamento propio de un medico externo, con la misma forma que el sincronizado."""

    def to_representation(self, medicine):
        return {
            "source": "own",
            "id": medicine.id,
            "medicine": None,
            "doctor_medicine": medicine.id,
            "preference_id": None,
            "name": medicine.name,
            "presentation": medicine.presentation,
            "active_ingredient": medicine.active_ingredient,
            "commercial_house": medicine.commercial_house,
            "category": medicine.category,
            "notes": medicine.notes,
            "default_dosage": medicine.default_dosage,
            "default_frequency": medicine.default_frequency,
            "default_duration": medicine.default_duration,
            "default_instructions": medicine.default_instructions,
            "is_active": medicine.is_active,
        }
