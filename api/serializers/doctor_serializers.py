from rest_framework import serializers

from api.models import DoctorMedicinePreference, DoctorPortalProfile, NursePortalProfile, SecretaryPortalProfile
from api.services.doctor_display import format_doctor_display_name


class DoctorPortalProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, doctor):
        return format_doctor_display_name(doctor.full_name, doctor.sex)

    class Meta:
        model = DoctorPortalProfile
        fields = [
            "id",
            "interactive_core_doctor_id",
            "full_name",
            "display_name",
            "sex",
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
            "display_name",
            "sex",
            "colegiation_code",
            "qualification_code",
            "final_score",
            "country",
            "company",
            "zone",
            "specialties",
            "is_top_doctor",
            "status",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]


class SecretaryPortalProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecretaryPortalProfile
        fields = [
            "id",
            "secretaria_interactivecore_id",
            "full_name",
            "email",
            "phone",
            "country",
            "status",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class NursePortalProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = NursePortalProfile
        fields = [
            "id",
            "interactive_core_user_id",
            "interactive_core_employee_id",
            "full_name",
            "email",
            "phone",
            "country",
            "status",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


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
