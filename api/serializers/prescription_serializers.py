from django.db import transaction
from rest_framework import serializers

from api.models import Prescription, PrescriptionItem


class PrescriptionItemSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(source="medicine.name", read_only=True)

    class Meta:
        model = PrescriptionItem
        fields = [
            "id",
            "medicine",
            "medicine_name",
            "dosage",
            "frequency",
            "duration",
            "instructions",
            "sort_order",
        ]


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
            medicine = item.get("medicine")
            if doctor and medicine and medicine.country_id != doctor.country_id:
                raise serializers.ValidationError({"items": "Todos los medicamentos deben pertenecer al pais del doctor."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        prescription = Prescription.objects.create(**validated_data)
        for index, item_data in enumerate(items_data):
            PrescriptionItem.objects.create(
                prescription=prescription,
                sort_order=item_data.pop("sort_order", index),
                **item_data,
            )
        return prescription
