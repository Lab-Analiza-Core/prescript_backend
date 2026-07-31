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
