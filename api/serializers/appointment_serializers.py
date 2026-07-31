from rest_framework import serializers

from api.models import Appointment


class AppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id",
            "doctor",
            "patient",
            "patient_name",
            "scheduled_at",
            "duration_minutes",
            "status",
            "reason",
            "clinical_notes",
            "commercial_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "doctor", "created_at", "updated_at"]
