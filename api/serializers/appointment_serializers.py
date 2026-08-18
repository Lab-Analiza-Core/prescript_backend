from django.utils import timezone
from rest_framework import serializers

from api.models import Appointment, DoctorPortalProfile, PatientVitals
from api.roles import PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_SECRETARY
from api.services.role_access import get_current_prescript_role
from api.services.secretary_access import get_secretary_assigned_interactive_core_doctor_ids


APPOINTMENT_TIME_CONFLICT_MESSAGE = (
    "Ese horario ya esta ocupado para este doctor. "
    "Elige otra hora disponible para continuar."
)
ACTIVE_APPOINTMENT_STATUSES = ("scheduled", "rescheduled")


class AppointmentSerializer(serializers.ModelSerializer):
    doctor = serializers.PrimaryKeyRelatedField(queryset=DoctorPortalProfile.objects.all(), required=False)
    doctor_name = serializers.CharField(source="doctor.full_name", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    patient_phone = serializers.CharField(source="patient.phone", read_only=True)
    last_preclinic_at = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            "id",
            "doctor",
            "doctor_name",
            "patient",
            "patient_name",
            "patient_phone",
            "scheduled_at",
            "duration_minutes",
            "status",
            "reason",
            "clinical_notes",
            "commercial_notes",
            "last_preclinic_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "last_preclinic_at"]

    def get_last_preclinic_at(self, obj):
        annotated_value = getattr(obj, "last_preclinic_recorded_at", None)
        if annotated_value is not None:
            return annotated_value
        latest = PatientVitals.objects.filter(patient=obj.patient).order_by("-recorded_at").first()
        return latest.recorded_at if latest else None

    def _current_role(self):
        request = self.context.get("request")
        if not request or not request.user:
            return ""
        return get_current_prescript_role(request.user)

    def _current_doctor(self):
        request = self.context.get("request")
        if not request or not request.user:
            return None
        return getattr(request.user, "doctor_portal_profile", None)

    def _has_time_conflict(self, doctor, scheduled_at, duration_minutes):
        appointment_end = scheduled_at + timezone.timedelta(minutes=duration_minutes)
        appointments = Appointment.objects.filter(
            doctor=doctor,
            scheduled_at__date=scheduled_at.date(),
            status__in=ACTIVE_APPOINTMENT_STATUSES,
        )
        if self.instance:
            appointments = appointments.exclude(pk=self.instance.pk)

        for appointment in appointments.only("scheduled_at", "duration_minutes"):
            existing_start = appointment.scheduled_at
            existing_end = existing_start + timezone.timedelta(minutes=appointment.duration_minutes)
            if existing_start < appointment_end and existing_end > scheduled_at:
                return True
        return False

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        incoming_fields = set(getattr(self, "initial_data", {}) or {})
        role = self._current_role()
        current_doctor = self._current_doctor()

        if role not in {PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_SECRETARY}:
            raise serializers.ValidationError({"detail": "Solo secretaria y doctor pueden gestionar citas."})

        if role == PRESCRIPT_ROLE_DOCTOR:
            if not current_doctor:
                raise serializers.ValidationError({"doctor": "El usuario doctor no tiene perfil medico en Prescript."})
            attrs["doctor"] = current_doctor
        elif self.instance:
            attrs["doctor"] = self.instance.doctor
        elif not attrs.get("doctor"):
            raise serializers.ValidationError({"doctor": "Seleccione el doctor para la cita."})

        doctor = attrs.get("doctor") or getattr(self.instance, "doctor", None)
        patient = attrs.get("patient") or getattr(self.instance, "patient", None)
        scheduled_at = attrs.get("scheduled_at") or getattr(self.instance, "scheduled_at", None)
        duration_minutes = attrs.get("duration_minutes") or getattr(self.instance, "duration_minutes", 30)

        if doctor and patient and patient.doctor_id != doctor.id:
            raise serializers.ValidationError({"patient": "El paciente no pertenece al doctor seleccionado."})

        is_scheduling = self.instance is None or bool({"scheduled_at", "patient", "doctor"} & incoming_fields)
        if is_scheduling and patient and scheduled_at:
            if scheduled_at < timezone.now():
                raise serializers.ValidationError(
                    {"scheduled_at": "No se pueden programar citas en fechas u horas anteriores a la actual."}
                )

            if doctor and self._has_time_conflict(doctor, scheduled_at, duration_minutes):
                raise serializers.ValidationError({"scheduled_at": APPOINTMENT_TIME_CONFLICT_MESSAGE})

            has_preclinic = PatientVitals.objects.filter(patient=patient, recorded_at__lte=scheduled_at).exists()
            if not has_preclinic:
                raise serializers.ValidationError(
                    {"patient": "Solo se pueden programar citas despues de registrar preclinica para el paciente."}
                )

        if role == PRESCRIPT_ROLE_SECRETARY and doctor:
            doctor_ids = get_secretary_assigned_interactive_core_doctor_ids(request.user)
            if doctor.interactive_core_doctor_id not in doctor_ids:
                raise serializers.ValidationError({"doctor": "El doctor no esta vinculado a esta secretaria."})

        return attrs
