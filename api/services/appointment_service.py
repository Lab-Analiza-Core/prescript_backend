from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from api.models import Appointment


ACTIVE_APPOINTMENT_STATUSES = ("scheduled", "rescheduled")
MAX_APPOINTMENT_DURATION_MINUTES = 1440
APPOINTMENT_TIME_CONFLICT_MESSAGE = (
    "Ese horario ya esta ocupado para este doctor. "
    "Elige otra hora disponible para continuar."
)


def appointment_has_time_conflict(*, doctor, scheduled_at, duration_minutes, exclude_pk=None):
    appointment_end = scheduled_at + timezone.timedelta(minutes=duration_minutes)
    earliest_possible_start = scheduled_at - timezone.timedelta(
        minutes=MAX_APPOINTMENT_DURATION_MINUTES
    )
    appointments = Appointment.objects.filter(
        doctor=doctor,
        scheduled_at__gt=earliest_possible_start,
        scheduled_at__lt=appointment_end,
        status__in=ACTIVE_APPOINTMENT_STATUSES,
    )
    if exclude_pk:
        appointments = appointments.exclude(pk=exclude_pk)

    for appointment in appointments.only("scheduled_at", "duration_minutes"):
        existing_start = appointment.scheduled_at
        existing_end = existing_start + timezone.timedelta(minutes=appointment.duration_minutes)
        if existing_start < appointment_end and existing_end > scheduled_at:
            return True
    return False


def acquire_doctor_schedule_lock(doctor_id):
    """Serialize schedule writes for one doctor for the current transaction."""
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            [f"prescript:doctor-schedule:{doctor_id}"],
        )


def save_appointment(serializer):
    with transaction.atomic():
        is_scheduling_change = serializer.instance is None or bool(
            {"scheduled_at", "duration_minutes"} & serializer.validated_data.keys()
        )
        if not is_scheduling_change:
            return serializer.save()

        doctor = serializer.validated_data.get("doctor") or serializer.instance.doctor
        scheduled_at = serializer.validated_data.get("scheduled_at") or serializer.instance.scheduled_at
        duration_minutes = serializer.validated_data.get("duration_minutes")
        if duration_minutes is None:
            duration_minutes = getattr(serializer.instance, "duration_minutes", 30)

        acquire_doctor_schedule_lock(doctor.pk)
        if appointment_has_time_conflict(
            doctor=doctor,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,
            exclude_pk=getattr(serializer.instance, "pk", None),
        ):
            raise ValidationError({"scheduled_at": APPOINTMENT_TIME_CONFLICT_MESSAGE})
        return serializer.save()
