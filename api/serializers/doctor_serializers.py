from rest_framework import serializers

from api.models import DoctorMedicinePreference, DoctorPortalProfile, NursePortalProfile, SecretaryPortalProfile
from api.services.doctor_display import format_doctor_display_name
from api.serializers.country_serializers import CountrySerializer


class DoctorPortalProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    display_name = serializers.SerializerMethodField()
    country = CountrySerializer(read_only=True)
    is_external = serializers.SerializerMethodField()

    def get_display_name(self, doctor):
        return format_doctor_display_name(doctor.full_name, doctor.sex)

    def get_is_external(self, doctor):
        return doctor.origin == "self_registered"

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
            "clinics",
            "preferences",
            "is_top_doctor",
            "is_external",
            "status",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "is_external",
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
            "clinics",
            "is_top_doctor",
            "status",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]


class SecretaryPortalProfileSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)

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
    country = CountrySerializer(read_only=True)

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

    def validate_medicine(self, medicine):
        request = self.context.get("request")
        doctor = getattr(getattr(request, "user", None), "doctor_portal_profile", None)
        if doctor and medicine.country_id != doctor.country_id:
            raise serializers.ValidationError("El medicamento no pertenece al pais del doctor.")
        return medicine
