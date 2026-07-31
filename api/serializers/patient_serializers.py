from rest_framework import serializers

from api.models import Patient, PatientMedicalProfile, PatientVitals


class PatientMedicalProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientMedicalProfile
        fields = [
            "id",
            "allergies",
            "chronic_conditions",
            "blood_type",
            "clinical_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PatientSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    medical_profile = PatientMedicalProfileSerializer(required=False)
    latest_vitals = serializers.SerializerMethodField()
    recent_vitals = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = [
            "id",
            "doctor",
            "first_name",
            "last_name",
            "full_name",
            "dni",
            "phone",
            "email",
            "birth_date",
            "sex",
            "commercial_notes",
            "patient_score",
            "is_active",
            "medical_profile",
            "latest_vitals",
            "recent_vitals",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "doctor", "patient_score", "created_at", "updated_at"]

    def get_latest_vitals(self, obj):
        latest = obj.vitals.order_by("-recorded_at").first()
        return PatientVitalsSerializer(latest).data if latest else None

    def get_recent_vitals(self, obj):
        vitals = obj.vitals.order_by("-recorded_at")[:5]
        return PatientVitalsSerializer(vitals, many=True).data

    def create(self, validated_data):
        profile_data = validated_data.pop("medical_profile", None)
        patient = super().create(validated_data)
        if profile_data:
            PatientMedicalProfile.objects.create(patient=patient, **profile_data)
        else:
            PatientMedicalProfile.objects.create(patient=patient)
        return patient

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("medical_profile", None)
        patient = super().update(instance, validated_data)
        if profile_data is not None:
            PatientMedicalProfile.objects.update_or_create(
                patient=patient,
                defaults=profile_data,
            )
        return patient


class PatientVitalsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientVitals
        fields = [
            "id",
            "patient",
            "appointment",
            "blood_pressure_systolic",
            "blood_pressure_diastolic",
            "oxygen_saturation",
            "temperature",
            "height_cm",
            "weight_kg",
            "recorded_at",
        ]
        read_only_fields = ["id", "recorded_at"]


class PreclinicVitalsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientVitals
        fields = [
            "id",
            "patient",
            "appointment",
            "blood_pressure_systolic",
            "blood_pressure_diastolic",
            "oxygen_saturation",
            "temperature",
            "height_cm",
            "weight_kg",
            "recorded_at",
        ]
        read_only_fields = ["id", "patient", "appointment", "recorded_at"]
