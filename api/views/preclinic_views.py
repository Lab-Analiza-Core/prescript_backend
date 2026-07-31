from django.utils import timezone
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models import Appointment, Patient, PatientVitals
from api.roles import PRESCRIPT_ROLE_ADMIN, PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_NURSE, get_primary_prescript_role
from api.serializers.patient_serializers import PreclinicVitalsSerializer


def _current_role(user):
    role = get_primary_prescript_role(user.groups.values_list("name", flat=True))
    if not role and (user.is_staff or user.is_superuser):
        return PRESCRIPT_ROLE_ADMIN
    return role


def _is_pediatric_appointment(appointment):
    specialties = appointment.doctor.specialties or []
    for specialty in specialties:
        text = " ".join(str(value) for value in specialty.values()).lower()
        if "pedi" in text:
            return True
    return False


def _accessible_appointments(user):
    queryset = Appointment.objects.select_related("doctor", "patient", "vitals").order_by("scheduled_at")
    doctor = getattr(user, "doctor_portal_profile", None)
    if doctor:
        return queryset.filter(doctor=doctor)

    role = _current_role(user)
    if role in {PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_ADMIN}:
        return queryset

    return queryset.none()


def _accessible_patients(user):
    queryset = Patient.objects.select_related("doctor").filter(is_active=True).order_by("last_name", "first_name")
    doctor = getattr(user, "doctor_portal_profile", None)
    if doctor:
        return queryset.filter(doctor=doctor)

    role = _current_role(user)
    if role in {PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_ADMIN}:
        return queryset

    return queryset.none()


def _is_pediatric_patient(patient):
    specialties = patient.doctor.specialties or []
    for specialty in specialties:
        text = " ".join(str(value) for value in specialty.values()).lower()
        if "pedi" in text:
            return True
    return False


def _comparison_vitals(appointment):
    latest = (
        PatientVitals.objects.filter(patient=appointment.patient)
        .exclude(appointment=appointment)
        .order_by("-recorded_at")
        .first()
    )
    if not latest:
        return None

    return {
        "blood_pressure_systolic": latest.blood_pressure_systolic,
        "blood_pressure_diastolic": latest.blood_pressure_diastolic,
        "height_cm": latest.height_cm,
        "weight_kg": latest.weight_kg,
        "recorded_at": latest.recorded_at,
    }


def _patient_comparison_vitals(patient, current_vitals=None):
    queryset = PatientVitals.objects.filter(patient=patient).order_by("-recorded_at")
    if current_vitals:
        queryset = queryset.exclude(pk=current_vitals.pk)
    latest = queryset.first()
    if not latest:
        return None

    return {
        "blood_pressure_systolic": latest.blood_pressure_systolic,
        "blood_pressure_diastolic": latest.blood_pressure_diastolic,
        "height_cm": latest.height_cm,
        "weight_kg": latest.weight_kg,
        "recorded_at": latest.recorded_at,
    }


def _appointment_payload(appointment):
    current_vitals = getattr(appointment, "vitals", None)
    return {
        "id": appointment.id,
        "patient": appointment.patient_id,
        "patient_name": appointment.patient.full_name,
        "patient_dni": appointment.patient.dni,
        "patient_birth_date": appointment.patient.birth_date,
        "patient_registered_at": appointment.patient.created_at,
        "doctor_name": appointment.doctor.full_name,
        "scheduled_at": appointment.scheduled_at,
        "status": appointment.status,
        "reason": appointment.reason,
        "is_pediatric": _is_pediatric_appointment(appointment),
        "current_vitals": PreclinicVitalsSerializer(current_vitals).data if current_vitals else None,
        "comparison_vitals": _comparison_vitals(appointment),
    }


def _patient_payload(patient, date=None):
    current_vitals = None
    if date:
        current_vitals = (
            PatientVitals.objects.filter(patient=patient, appointment__isnull=True, recorded_at__date=date)
            .order_by("-recorded_at")
            .first()
        )

    return {
        "id": patient.id,
        "patient": patient.id,
        "patient_name": patient.full_name,
        "patient_dni": patient.dni,
        "patient_birth_date": patient.birth_date,
        "patient_registered_at": patient.created_at,
        "doctor_name": patient.doctor.full_name,
        "scheduled_at": None,
        "status": "registered",
        "reason": "Paciente registrado",
        "is_pediatric": _is_pediatric_patient(patient),
        "current_vitals": PreclinicVitalsSerializer(current_vitals).data if current_vitals else None,
        "comparison_vitals": _patient_comparison_vitals(patient, current_vitals),
        "source": "patient",
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def preclinic_appointment_list_view(request):
    queryset = _accessible_appointments(request.user)
    date = request.query_params.get("date") or timezone.localdate().isoformat()
    queryset = queryset.filter(scheduled_at__date=date)
    return Response([_appointment_payload(appointment) for appointment in queryset])


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def preclinic_patient_list_view(request):
    date = request.query_params.get("date") or timezone.localdate().isoformat()
    queryset = _accessible_patients(request.user)
    search = request.query_params.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(dni__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
        )
    return Response([_patient_payload(patient, date) for patient in queryset[:50]])


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def preclinic_vitals_upsert_view(request, appointment_id):
    try:
        appointment = _accessible_appointments(request.user).get(pk=appointment_id)
    except Appointment.DoesNotExist:
        return Response({"detail": "Cita no encontrada para preclinica."}, status=status.HTTP_404_NOT_FOUND)

    payload = request.data.copy()
    if not _is_pediatric_appointment(appointment):
        payload["height_cm"] = None

    instance = getattr(appointment, "vitals", None)
    serializer = PreclinicVitalsSerializer(instance, data=payload, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(patient=appointment.patient, appointment=appointment)

    return Response(_appointment_payload(appointment))


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def preclinic_patient_vitals_upsert_view(request, patient_id):
    try:
        patient = _accessible_patients(request.user).get(pk=patient_id)
    except Patient.DoesNotExist:
        return Response({"detail": "Paciente no encontrado para preclinica."}, status=status.HTTP_404_NOT_FOUND)

    payload = request.data.copy()
    if not _is_pediatric_patient(patient):
        payload["height_cm"] = None

    today = timezone.localdate()
    instance = (
        PatientVitals.objects.filter(patient=patient, appointment__isnull=True, recorded_at__date=today)
        .order_by("-recorded_at")
        .first()
    )
    serializer = PreclinicVitalsSerializer(instance, data=payload, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(patient=patient, appointment=None)

    return Response(_patient_payload(patient, today.isoformat()))
