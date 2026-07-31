from rest_framework import serializers

from api.models import DoctorMedicinePreference, DoctorPortalProfile


class DoctorPortalProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = DoctorPortalProfile
        fields = [
            "id",
            "interactive_core_doctor_id",
            "full_name",
            "colegiation_code",
            "qualification_code",
            "final_score",
            "country",
            "company",
            "zone",
            "phone",
            "public_email",
            "email",
            "specialties",
            "preferences",
            "is_top_doctor",
            "status",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "interactive_core_doctor_id",
            "colegiation_code",
            "qualification_code",
            "final_score",
            "country",
            "company",
            "zone",
            "is_top_doctor",
            "status",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]


class DoctorMedicinePreferenceSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(source="medicine.name", read_only=True)

    class Meta:
        model = DoctorMedicinePreference
        fields = [
            "id",
            "doctor",
            "medicine",
            "medicine_name",
            "category",
            "commercial_house_priority",
            "sort_order",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "doctor", "created_at", "updated_at"]
