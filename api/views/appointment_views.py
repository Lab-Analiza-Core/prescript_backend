from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models import Appointment
from api.roles import PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_SECRETARY
from api.services.role_access import get_current_prescript_role
from api.serializers import AppointmentSerializer
from api.services.organization_scope import get_organization_scope
from api.services.secretary_access import get_secretary_assigned_doctor_ids
from api.services.country_scope import get_country_scope
from api.services.appointment_service import (
    ACTIVE_APPOINTMENT_STATUSES,
    APPOINTMENT_TIME_CONFLICT_MESSAGE,
    acquire_doctor_schedule_lock,
    appointment_has_time_conflict,
    save_appointment,
)


def appointment_queryset_for_request(request):
    role = get_current_prescript_role(request.user)
    doctor = getattr(request.user, "doctor_portal_profile", None)
    queryset = Appointment.objects.select_related("doctor", "patient").annotate(
        last_preclinic_recorded_at=Max("patient__vitals__recorded_at")
    )
    queryset = get_country_scope(request).require_valid().filter(
        queryset,
        field="doctor__country_id",
    )
    queryset = get_organization_scope(request.user).filter(queryset, field="doctor__organization")

    if role == PRESCRIPT_ROLE_DOCTOR and doctor:
        return queryset.filter(doctor=doctor)
    if role == PRESCRIPT_ROLE_SECRETARY:
        return queryset.filter(doctor_id__in=get_secretary_assigned_doctor_ids(request.user))
    return queryset.none()


class AppointmentListCreateView(generics.ListCreateAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = appointment_queryset_for_request(self.request)

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        pending_closure = self.request.query_params.get("pending_closure") == "true"
        if pending_closure:
            return queryset.filter(
                status__in=ACTIVE_APPOINTMENT_STATUSES,
                scheduled_at__lt=timezone.now(),
            )
        if date_from:
            queryset = queryset.filter(scheduled_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(scheduled_at__date__lte=date_to)
        return queryset

    def perform_create(self, serializer):
        role = get_current_prescript_role(self.request.user)
        if role not in {PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_SECRETARY}:
            raise PermissionDenied("Solo secretaria y doctor pueden gestionar citas.")
        save_appointment(serializer)


class AppointmentDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return appointment_queryset_for_request(self.request)

    def perform_update(self, serializer):
        save_appointment(serializer)


class AppointmentPastRescheduleView(generics.GenericAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return appointment_queryset_for_request(self.request)

    def post(self, request, pk):
        appointment = self.get_object()
        appointment_end = appointment.scheduled_at + timezone.timedelta(minutes=appointment.duration_minutes)
        if appointment.status not in ACTIVE_APPOINTMENT_STATUSES:
            raise ValidationError({"status": "Solo una cita activa puede reprogramarse."})
        if appointment_end > timezone.now():
            raise ValidationError({"scheduled_at": "Esta accion se usa unicamente para citas cuyo horario ya finalizo."})

        payload = {
            "doctor": appointment.doctor_id,
            "patient": appointment.patient_id,
            "scheduled_at": request.data.get("scheduled_at"),
            "duration_minutes": request.data.get("duration_minutes", appointment.duration_minutes),
            "reason": request.data.get("reason", appointment.reason),
            "status": "scheduled",
        }
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            locked_appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
            if locked_appointment.status not in ACTIVE_APPOINTMENT_STATUSES:
                raise ValidationError({"status": "La cita ya fue cerrada por otro usuario."})
            acquire_doctor_schedule_lock(locked_appointment.doctor_id)
            if appointment_has_time_conflict(
                doctor=locked_appointment.doctor,
                scheduled_at=serializer.validated_data["scheduled_at"],
                duration_minutes=serializer.validated_data.get(
                    "duration_minutes", locked_appointment.duration_minutes
                ),
                exclude_pk=locked_appointment.pk,
            ):
                raise ValidationError({"scheduled_at": APPOINTMENT_TIME_CONFLICT_MESSAGE})
            replacement = serializer.save()
            locked_appointment.status = "superseded"
            locked_appointment.save(update_fields=["status", "updated_at"])

        return Response(self.get_serializer(replacement).data, status=status.HTTP_201_CREATED)
