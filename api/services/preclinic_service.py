from django.db.models import Prefetch
from django.utils import timezone

from api.models import Appointment, Patient, PatientMedicalProfile, PatientVitals
from api.roles import PRESCRIPT_ROLE_ADMIN, PRESCRIPT_ROLE_NURSE
from api.services.patient_access import country_scoped_patient_queryset
from api.services.role_access import get_current_prescript_role
from api.serializers.patient_serializers import PatientMedicalProfileSerializer, PreclinicVitalsSerializer


def is_future_date(value):
    return value > timezone.localdate()


def is_pediatric_specialty_holder(value):
    specialties = value.doctor.specialties or []
    for specialty in specialties:
        text = " ".join(str(item) for item in specialty.values()).lower()
        if "pedi" in text:
            return True
    return False


def accessible_appointments(user, scope):
    queryset = (
        Appointment.objects.select_related("doctor", "patient", "patient__medical_profile", "vitals")
        .prefetch_related(Prefetch("patient__vitals", queryset=PatientVitals.objects.order_by("-recorded_at")))
        .order_by("scheduled_at")
    )
    doctor = getattr(user, "doctor_portal_profile", None)
    if doctor:
        return scope.require_valid().filter(queryset.filter(doctor=doctor), field="doctor__country_id")

    role = get_current_prescript_role(user)
    if role in {PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_ADMIN}:
        return scope.require_valid().filter(queryset, field="doctor__country_id")

    return queryset.none()


def accessible_patients(user, scope):
    queryset = (
        Patient.objects.select_related("doctor", "medical_profile")
        .prefetch_related(Prefetch("vitals", queryset=PatientVitals.objects.order_by("-recorded_at")))
        .order_by("last_name", "first_name")
    )
    return country_scoped_patient_queryset(
        user,
        scope,
        queryset=queryset,
        include_inactive=False,
    )


def vitals_payload(vitals):
    return {
        "blood_pressure_systolic": vitals.blood_pressure_systolic,
        "blood_pressure_diastolic": vitals.blood_pressure_diastolic,
        "height_cm": vitals.height_cm,
        "weight_kg": vitals.weight_kg,
        "recorded_at": vitals.recorded_at,
    }


def medical_profile_payload(patient):
    try:
        profile = patient.medical_profile
    except PatientMedicalProfile.DoesNotExist:
        return {
            "allergies": [],
            "chronic_conditions": [],
            "blood_type": None,
            "clinical_notes": None,
        }
    return PatientMedicalProfileSerializer(profile).data


def comparison_vitals(appointment):
    prefetched_cache = getattr(appointment.patient, "_prefetched_objects_cache", {})
    if "vitals" in prefetched_cache:
        for vital in prefetched_cache["vitals"]:
            if vital.appointment_id != appointment.id:
                return vitals_payload(vital)
        return None

    latest = (
        PatientVitals.objects.filter(patient=appointment.patient)
        .exclude(appointment=appointment)
        .order_by("-recorded_at")
        .first()
    )
    return vitals_payload(latest) if latest else None


def patient_comparison_vitals(patient, current_vitals=None):
    prefetched_cache = getattr(patient, "_prefetched_objects_cache", {})
    if "vitals" in prefetched_cache:
        for vital in prefetched_cache["vitals"]:
            if not current_vitals or vital.pk != current_vitals.pk:
                return vitals_payload(vital)
        return None

    queryset = PatientVitals.objects.filter(patient=patient).order_by("-recorded_at")
    if current_vitals:
        queryset = queryset.exclude(pk=current_vitals.pk)
    latest = queryset.first()
    return vitals_payload(latest) if latest else None


def appointment_payload(appointment):
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
        "is_pediatric": is_pediatric_specialty_holder(appointment),
        "medical_profile": medical_profile_payload(appointment.patient),
        "current_vitals": PreclinicVitalsSerializer(current_vitals).data if current_vitals else None,
        "comparison_vitals": comparison_vitals(appointment),
    }


def current_patient_vitals_for_date(patient, selected_date):
    prefetched_cache = getattr(patient, "_prefetched_objects_cache", {})
    if "vitals" in prefetched_cache:
        return next(
            (
                vital
                for vital in prefetched_cache["vitals"]
                if vital.appointment_id is None and timezone.localdate(vital.recorded_at) == selected_date
            ),
            None,
        )

    return (
        PatientVitals.objects.filter(patient=patient, appointment__isnull=True, recorded_at__date=selected_date)
        .order_by("-recorded_at")
        .first()
    )


def patient_payload(patient, selected_date=None):
    current_vitals = current_patient_vitals_for_date(patient, selected_date) if selected_date else None
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
        "is_pediatric": is_pediatric_specialty_holder(patient),
        "medical_profile": medical_profile_payload(patient),
        "current_vitals": PreclinicVitalsSerializer(current_vitals).data if current_vitals else None,
        "comparison_vitals": patient_comparison_vitals(patient, current_vitals),
        "source": "patient",
    }
