from rest_framework import serializers

from api.models import DoctorPortalProfile, Patient, PatientMedicalProfile, PatientVitals
from api.utils.field_validators import validate_and_format_dni, validate_and_format_phone


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
    doctor = serializers.PrimaryKeyRelatedField(queryset=DoctorPortalProfile.objects.all(), required=False)
    full_name = serializers.CharField(read_only=True)
    doctor_name = serializers.CharField(source="doctor.full_name", read_only=True)
    doctor_is_external = serializers.SerializerMethodField()
    medical_profile = PatientMedicalProfileSerializer(required=False)
    latest_vitals = serializers.SerializerMethodField()
    recent_vitals = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = [
            "id",
            "doctor",
            "doctor_name",
            "doctor_is_external",
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
        read_only_fields = ["id", "doctor_name", "doctor_is_external", "patient_score", "created_at", "updated_at"]

    def get_doctor_is_external(self, obj):
        return obj.doctor.origin == "self_registered"

    def get_latest_vitals(self, obj):
        latest = obj.vitals.order_by("-recorded_at").first()
        return PatientVitalsSerializer(latest).data if latest else None

    def get_recent_vitals(self, obj):
        vitals = obj.vitals.order_by("-recorded_at")[:5]
        return PatientVitalsSerializer(vitals, many=True).data

    def _get_validation_country(self, attrs=None):
        attrs = attrs or {}
        doctor = attrs.get("doctor")
        if not doctor and self.instance:
            doctor = self.instance.doctor
        if not doctor:
            request = self.context.get("request")
            doctor = getattr(getattr(request, "user", None), "doctor_portal_profile", None)
        return getattr(doctor, "country", None) or "HN"

    def validate(self, attrs):
        country = self._get_validation_country(attrs)
        errors = {}
        if "dni" in attrs:
            try:
                attrs["dni"] = validate_and_format_dni(attrs.get("dni"), country=country)
            except serializers.ValidationError as exc:
                errors["dni"] = exc.detail
        if "phone" in attrs:
            try:
                attrs["phone"] = validate_and_format_phone(attrs.get("phone"), country=country)
            except serializers.ValidationError as exc:
                errors["phone"] = exc.detail
        if errors:
            raise serializers.ValidationError(errors)

        doctor = attrs.get("doctor")
        if not doctor and self.instance:
            doctor = self.instance.doctor
        if not doctor:
            request = self.context.get("request")
            doctor = getattr(getattr(request, "user", None), "doctor_portal_profile", None)
        dni = attrs.get("dni", getattr(self.instance, "dni", None))
        if doctor and dni:
            queryset = Patient.objects.filter(doctor=doctor, dni=dni)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError({"dni": "Ya existe un paciente con este DNI para el doctor seleccionado."})

        return attrs

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
