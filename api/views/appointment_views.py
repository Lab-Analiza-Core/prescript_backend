from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from django.db.models import Max

from api.models import Appointment
from api.roles import PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_SECRETARY
from api.services.role_access import get_current_prescript_role
from api.serializers import AppointmentSerializer
from api.services.secretary_access import get_secretary_assigned_interactive_core_doctor_ids


class AppointmentListCreateView(generics.ListCreateAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = get_current_prescript_role(self.request.user)
        doctor = getattr(self.request.user, "doctor_portal_profile", None)
        queryset = Appointment.objects.select_related("doctor", "patient").annotate(
            last_preclinic_recorded_at=Max("patient__vitals__recorded_at")
        )

        if role == PRESCRIPT_ROLE_DOCTOR and doctor:
            queryset = queryset.filter(doctor=doctor)
        elif role == PRESCRIPT_ROLE_SECRETARY:
            doctor_ids = get_secretary_assigned_interactive_core_doctor_ids(self.request.user)
            queryset = queryset.filter(doctor__interactive_core_doctor_id__in=doctor_ids)
        else:
            queryset = queryset.none()

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        if date_from:
            queryset = queryset.filter(scheduled_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(scheduled_at__date__lte=date_to)
        return queryset

    def perform_create(self, serializer):
        role = get_current_prescript_role(self.request.user)
        if role not in {PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_SECRETARY}:
            raise PermissionDenied("Solo secretaria y doctor pueden gestionar citas.")
        serializer.save()


class AppointmentDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = get_current_prescript_role(self.request.user)
        doctor = getattr(self.request.user, "doctor_portal_profile", None)
        queryset = Appointment.objects.select_related("doctor", "patient").annotate(
            last_preclinic_recorded_at=Max("patient__vitals__recorded_at")
        )

        if role == PRESCRIPT_ROLE_DOCTOR and doctor:
            return queryset.filter(doctor=doctor)
        if role == PRESCRIPT_ROLE_SECRETARY:
            doctor_ids = get_secretary_assigned_interactive_core_doctor_ids(self.request.user)
            return queryset.filter(doctor__interactive_core_doctor_id__in=doctor_ids)
        return queryset.none()
