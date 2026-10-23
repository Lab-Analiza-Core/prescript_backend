from rest_framework.exceptions import PermissionDenied

from api.models import Patient
from api.roles import (
    PRESCRIPT_ROLE_ADMIN,
    PRESCRIPT_ROLE_DOCTOR,
    PRESCRIPT_ROLE_MANAGER,
    PRESCRIPT_ROLE_NURSE,
    PRESCRIPT_ROLE_SECRETARY,
)
from api.services.role_access import get_current_prescript_role
from api.services.organization_scope import get_organization_scope
from api.services.secretary_access import get_secretary_assigned_doctor_ids


PATIENT_MANAGER_ROLES = {PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_ADMIN, PRESCRIPT_ROLE_MANAGER}


def accessible_patient_queryset(user, queryset=None, include_inactive=True):
    queryset = queryset or Patient.objects.select_related("doctor", "medical_profile")
    doctor = getattr(user, "doctor_portal_profile", None)
    if doctor:
        queryset = queryset.filter(doctor=doctor)
    else:
        role = get_current_prescript_role(user)
        if role == PRESCRIPT_ROLE_SECRETARY:
            queryset = queryset.filter(doctor_id__in=get_secretary_assigned_doctor_ids(user))
        elif role not in PATIENT_MANAGER_ROLES:
            queryset = queryset.none()

    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset


def country_scoped_patient_queryset(user, scope, queryset=None, include_inactive=True):
    queryset = accessible_patient_queryset(
        user,
        queryset=queryset,
        include_inactive=include_inactive,
    )
    queryset = scope.require_valid().filter(queryset, field="doctor__country_id")
    return get_organization_scope(user).filter(queryset, field="doctor__organization")


def save_patient_for_user(serializer, user, patient=None, scope=None):
    role = get_current_prescript_role(user)
    doctor = getattr(user, "doctor_portal_profile", None)

    if role == PRESCRIPT_ROLE_DOCTOR and doctor:
        if scope and not scope.require_valid().allows(doctor.country_id):
            raise PermissionDenied("El doctor no pertenece al pais activo.")
        serializer.save(doctor=doctor)
        return

    if role == PRESCRIPT_ROLE_SECRETARY:
        selected_doctor = serializer.validated_data.get("doctor", getattr(patient, "doctor", None))
        if not selected_doctor:
            raise PermissionDenied("Seleccione el doctor responsable del paciente.")
        if selected_doctor.id not in get_secretary_assigned_doctor_ids(user):
            raise PermissionDenied("El doctor no esta vinculado a esta secretaria.")
        if scope and not scope.require_valid().allows(selected_doctor.country_id):
            raise PermissionDenied("El doctor no pertenece al pais activo.")
        serializer.save()
        return

    if role in PATIENT_MANAGER_ROLES:
        selected_doctor = serializer.validated_data.get("doctor", getattr(patient, "doctor", None))
        if not selected_doctor:
            raise PermissionDenied("Seleccione el doctor responsable del paciente.")
        if not get_organization_scope(user).allows_organization(selected_doctor.organization_id):
            raise PermissionDenied("El doctor no pertenece a su organizacion.")
        if scope and not scope.require_valid().allows(selected_doctor.country_id):
            raise PermissionDenied("El doctor no pertenece al pais activo.")
        serializer.save()
        return

    raise PermissionDenied("No puede registrar pacientes." if patient is None else "No puede modificar pacientes.")
