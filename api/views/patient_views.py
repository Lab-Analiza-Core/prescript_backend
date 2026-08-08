from rest_framework import generics
from rest_framework.exceptions import PermissionDenied

from api.models import Patient, PatientVitals
from api.roles import (
    PRESCRIPT_ROLE_ADMIN,
    PRESCRIPT_ROLE_DOCTOR,
    PRESCRIPT_ROLE_MANAGER,
    PRESCRIPT_ROLE_NURSE,
    PRESCRIPT_ROLE_SECRETARY,
    get_primary_prescript_role,
)
from api.serializers import PatientSerializer, PatientVitalsSerializer
from api.services.secretary_access import get_secretary_assigned_interactive_core_doctor_ids
from api.views.doctor_views import get_current_doctor


def _current_role(user):
    role = get_primary_prescript_role(user.groups.values_list("name", flat=True))
    if not role and (user.is_staff or user.is_superuser):
        return PRESCRIPT_ROLE_ADMIN
    if not role and getattr(user, "doctor_portal_profile", None):
        return PRESCRIPT_ROLE_DOCTOR
    if not role and getattr(user, "secretary_portal_profile", None):
        return PRESCRIPT_ROLE_SECRETARY
    if not role and getattr(user, "nurse_portal_profile", None):
        return PRESCRIPT_ROLE_NURSE
    return role


def _accessible_patients(user):
    queryset = Patient.objects.select_related("doctor", "medical_profile")
    doctor = getattr(user, "doctor_portal_profile", None)
    if doctor:
        return queryset.filter(doctor=doctor)

    role = _current_role(user)
    if role == PRESCRIPT_ROLE_SECRETARY:
        doctor_ids = get_secretary_assigned_interactive_core_doctor_ids(user)
        return queryset.filter(doctor__interactive_core_doctor_id__in=doctor_ids)

    if role in {PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_ADMIN, PRESCRIPT_ROLE_MANAGER}:
        return queryset

    return queryset.none()


class PatientListCreateView(generics.ListCreateAPIView):
    serializer_class = PatientSerializer

    def get_queryset(self):
        queryset = _accessible_patients(self.request.user)
        include_inactive = self.request.query_params.get("include_inactive") == "true"
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        return queryset

    def perform_create(self, serializer):
        role = _current_role(self.request.user)
        doctor = getattr(self.request.user, "doctor_portal_profile", None)
        if role == PRESCRIPT_ROLE_DOCTOR and doctor:
            serializer.save(doctor=doctor)
            return
        if role == PRESCRIPT_ROLE_SECRETARY:
            doctor = serializer.validated_data.get("doctor")
            doctor_ids = get_secretary_assigned_interactive_core_doctor_ids(self.request.user)
            if not doctor:
                raise PermissionDenied("Seleccione el doctor responsable del paciente.")
            if doctor.interactive_core_doctor_id not in doctor_ids:
                raise PermissionDenied("El doctor no esta vinculado a esta secretaria.")
            serializer.save()
            return
        if role in {PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_ADMIN, PRESCRIPT_ROLE_MANAGER}:
            doctor = serializer.validated_data.get("doctor")
            if not doctor:
                raise PermissionDenied("Seleccione el doctor responsable del paciente.")
            serializer.save()
            return
        raise PermissionDenied("No puede registrar pacientes.")


class PatientDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = PatientSerializer

    def get_queryset(self):
        return _accessible_patients(self.request.user).select_related("medical_profile")

    def perform_update(self, serializer):
        patient = self.get_object()
        role = _current_role(self.request.user)
        doctor = getattr(self.request.user, "doctor_portal_profile", None)

        if role == PRESCRIPT_ROLE_DOCTOR and doctor:
            serializer.save(doctor=doctor)
            return
        if role == PRESCRIPT_ROLE_SECRETARY:
            selected_doctor = serializer.validated_data.get("doctor", patient.doctor)
            doctor_ids = get_secretary_assigned_interactive_core_doctor_ids(self.request.user)
            if selected_doctor.interactive_core_doctor_id not in doctor_ids:
                raise PermissionDenied("El doctor no esta vinculado a esta secretaria.")
            serializer.save()
            return
        if role in {PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_ADMIN, PRESCRIPT_ROLE_MANAGER}:
            serializer.save()
            return
        raise PermissionDenied("No puede modificar pacientes.")


class PatientVitalsListCreateView(generics.ListCreateAPIView):
    serializer_class = PatientVitalsSerializer

    def get_queryset(self):
        return PatientVitals.objects.filter(
            patient__doctor=get_current_doctor(self.request.user),
        ).select_related("patient", "appointment")

    def perform_create(self, serializer):
        doctor = get_current_doctor(self.request.user)
        patient = serializer.validated_data["patient"]
        if patient.doctor_id != doctor.id:
            raise PermissionDenied("No puede registrar signos vitales de otro doctor.")
        serializer.save()
