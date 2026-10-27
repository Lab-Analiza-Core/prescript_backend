from django.db import transaction
from rest_framework import serializers

from api.models import Prescription, PrescriptionItem
from api.models.organization_models import ORIGIN_SELF_REGISTERED


class PrescriptionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = [
            "id",
            "medicine",
            "doctor_medicine",
            "medicine_name",
            "presentation",
            "active_ingredient",
            "dosage",
            "frequency",
            "duration",
            "instructions",
            "sort_order",
        ]
        read_only_fields = ["medicine_name", "presentation", "active_ingredient"]
        extra_kwargs = {
            "medicine": {"required": False, "allow_null": True},
            "doctor_medicine": {"required": False, "allow_null": True},
        }


class PrescriptionSerializer(serializers.ModelSerializer):
    items = PrescriptionItemSerializer(many=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)

    class Meta:
        model = Prescription
        fields = [
            "id",
            "doctor",
            "patient",
            "patient_name",
            "appointment",
            "diagnosis",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "doctor", "created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        doctor = getattr(getattr(request, "user", None), "doctor_portal_profile", None)
        patient = attrs.get("patient")
        appointment = attrs.get("appointment")
        items = attrs.get("items", [])
        if not items:
            raise serializers.ValidationError({"items": "La receta debe incluir al menos un medicamento."})
        if doctor and patient and patient.doctor_id != doctor.id:
            raise serializers.ValidationError({"patient": "El paciente no pertenece al doctor autenticado."})
        if doctor and appointment and appointment.doctor_id != doctor.id:
            raise serializers.ValidationError({"appointment": "La cita no pertenece al doctor autenticado."})
        if appointment and patient and appointment.patient_id != patient.id:
            raise serializers.ValidationError({"appointment": "La cita no pertenece al paciente seleccionado."})
        for item in items:
            self._validate_item_medicine(doctor, item)
        return attrs

    @staticmethod
    def _validate_item_medicine(doctor, item):
        medicine = item.get("medicine")
        doctor_medicine = item.get("doctor_medicine")
        if bool(medicine) == bool(doctor_medicine):
            raise serializers.ValidationError({"items": "Cada medicamento debe venir de un solo catalogo."})
        if not doctor:
            return
        if doctor.origin == ORIGIN_SELF_REGISTERED:
            if medicine:
                raise serializers.ValidationError({"items": "Use los medicamentos de su catalogo propio."})
            if doctor_medicine.doctor_id != doctor.id or not doctor_medicine.is_active:
                raise serializers.ValidationError({"items": "El medicamento no pertenece a su catalogo."})
        else:
            if doctor_medicine:
                raise serializers.ValidationError({"items": "Use los medicamentos del catalogo sincronizado."})
            if medicine.country_id != doctor.country_id:
                raise serializers.ValidationError({"items": "Todos los medicamentos deben pertenecer al pais del doctor."})

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        prescription = Prescription.objects.create(**validated_data)
        for index, item_data in enumerate(items_data):
            source = item_data.get("medicine") or item_data.get("doctor_medicine")
            PrescriptionItem.objects.create(
                prescription=prescription,
                sort_order=item_data.pop("sort_order", index),
                medicine_name=source.name,
                presentation=source.presentation or "",
                active_ingredient=source.active_ingredient or "",
                **item_data,
            )
        return prescription
