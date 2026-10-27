from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models import Appointment, Prescription
from api.roles import PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_SECRETARY
from api.services.country_scope import get_country_scope
from api.services.patient_access import country_scoped_patient_queryset
from api.services.role_access import get_current_prescript_role
from api.services.organization_scope import get_organization_scope
from api.services.secretary_access import get_secretary_assigned_doctor_ids


SEARCH_RESULT_LIMIT = 5


def _appointment_queryset(request):
    role = get_current_prescript_role(request.user)
    doctor = getattr(request.user, "doctor_portal_profile", None)
    queryset = Appointment.objects.select_related("doctor", "patient")
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


def _prescription_queryset(request):
    doctor = getattr(request.user, "doctor_portal_profile", None)
    if get_current_prescript_role(request.user) != PRESCRIPT_ROLE_DOCTOR or not doctor:
        return Prescription.objects.none()
    if not get_country_scope(request).require_valid().allows(doctor.country_id):
        return Prescription.objects.none()
    return Prescription.objects.filter(doctor=doctor).select_related("patient")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def global_search_view(request):
    term = str(request.query_params.get("q", "")).strip()[:100]
    if len(term) < 2:
        return Response({"query": term, "patients": [], "appointments": [], "prescriptions": []})

    patient_filter = (
        Q(first_name__icontains=term)
        | Q(last_name__icontains=term)
        | Q(dni__icontains=term)
        | Q(phone__icontains=term)
        | Q(email__icontains=term)
    )
    patients = list(
        country_scoped_patient_queryset(
            request.user,
            get_country_scope(request),
            include_inactive=False,
        )
        .filter(patient_filter)
        .select_related("doctor")
        .order_by("last_name", "first_name")[:SEARCH_RESULT_LIMIT]
    )

    appointment_filter = (
        Q(patient__first_name__icontains=term)
        | Q(patient__last_name__icontains=term)
        | Q(patient__dni__icontains=term)
        | Q(reason__icontains=term)
    )
    appointments = list(
        _appointment_queryset(request)
        .filter(appointment_filter)
        .order_by("-scheduled_at")[:SEARCH_RESULT_LIMIT]
    )

    prescription_filter = (
        Q(patient__first_name__icontains=term)
        | Q(patient__last_name__icontains=term)
        | Q(patient__dni__icontains=term)
        | Q(diagnosis__icontains=term)
        | Q(items__medicine_name__icontains=term)
    )
    if term.isdigit():
        prescription_filter |= Q(pk=int(term))
    prescriptions = list(
        _prescription_queryset(request)
        .filter(prescription_filter)
        .distinct()
        .order_by("-created_at")[:SEARCH_RESULT_LIMIT]
    )

    return Response(
        {
            "query": term,
            "patients": [
                {
                    "id": patient.id,
                    "name": patient.full_name,
                    "dni": patient.dni,
                    "phone": patient.phone,
                    "doctor_name": patient.doctor.full_name,
                }
                for patient in patients
            ],
            "appointments": [
                {
                    "id": appointment.id,
                    "patient_id": appointment.patient_id,
                    "patient_name": appointment.patient.full_name,
                    "scheduled_at": appointment.scheduled_at,
                    "reason": appointment.reason,
                    "status": appointment.status,
                    "doctor_name": appointment.doctor.full_name,
                }
                for appointment in appointments
            ],
            "prescriptions": [
                {
                    "id": prescription.id,
                    "patient_id": prescription.patient_id,
                    "patient_name": prescription.patient.full_name,
                    "diagnosis": prescription.diagnosis,
                    "created_at": prescription.created_at,
                }
                for prescription in prescriptions
            ],
        }
    )
