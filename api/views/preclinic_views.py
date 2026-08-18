from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models import Appointment, Patient, PatientVitals
from api.services.preclinic_service import (
    accessible_appointments,
    accessible_patients,
    appointment_payload,
    is_future_date,
    is_pediatric_specialty_holder,
    patient_payload,
)
from api.serializers.patient_serializers import PreclinicVitalsSerializer


def _requested_date(request):
    raw_date = request.query_params.get("date") or request.data.get("date") or timezone.localdate().isoformat()
    parsed_date = parse_date(raw_date)
    if not parsed_date:
        return None
    return parsed_date


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def preclinic_appointment_list_view(request):
    queryset = accessible_appointments(request.user)
    date = request.query_params.get("date") or timezone.localdate().isoformat()
    queryset = queryset.filter(scheduled_at__date=date)
    return Response([appointment_payload(appointment) for appointment in queryset])


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def preclinic_patient_list_view(request):
    date = request.query_params.get("date") or timezone.localdate().isoformat()
    selected_date = parse_date(date)
    queryset = accessible_patients(request.user)
    search = request.query_params.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(dni__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
        )
    return Response([patient_payload(patient, selected_date) for patient in queryset[:50]])


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def preclinic_vitals_upsert_view(request, appointment_id):
    try:
        appointment = accessible_appointments(request.user).get(pk=appointment_id)
    except Appointment.DoesNotExist:
        return Response({"detail": "Cita no encontrada para preclinica."}, status=status.HTTP_404_NOT_FOUND)

    if is_future_date(timezone.localdate(appointment.scheduled_at)):
        return Response(
            {"date": "No se pueden agregar datos de preclinica en fechas futuras."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    payload = request.data.copy()
    if not is_pediatric_specialty_holder(appointment):
        payload["height_cm"] = None

    instance = getattr(appointment, "vitals", None)
    serializer = PreclinicVitalsSerializer(instance, data=payload, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(patient=appointment.patient, appointment=appointment)

    return Response(appointment_payload(appointment))


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def preclinic_patient_vitals_upsert_view(request, patient_id):
    try:
        patient = accessible_patients(request.user).get(pk=patient_id)
    except Patient.DoesNotExist:
        return Response({"detail": "Paciente no encontrado para preclinica."}, status=status.HTTP_404_NOT_FOUND)

    payload = request.data.copy()
    if not is_pediatric_specialty_holder(patient):
        payload["height_cm"] = None

    selected_date = _requested_date(request)
    if not selected_date:
        return Response({"date": "Fecha invalida."}, status=status.HTTP_400_BAD_REQUEST)
    if is_future_date(selected_date):
        return Response(
            {"date": "No se pueden agregar datos de preclinica en fechas futuras."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    instance = (
        PatientVitals.objects.filter(patient=patient, appointment__isnull=True, recorded_at__date=selected_date)
        .order_by("-recorded_at")
        .first()
    )
    serializer = PreclinicVitalsSerializer(instance, data=payload, partial=True)
    serializer.is_valid(raise_exception=True)
    vitals = serializer.save(patient=patient, appointment=None)
    getattr(patient, "_prefetched_objects_cache", {}).pop("vitals", None)
    if not instance and selected_date != timezone.localdate():
        selected_datetime = timezone.make_aware(
            datetime.combine(selected_date, timezone.localtime().time()),
            timezone.get_current_timezone(),
        )
        PatientVitals.objects.filter(pk=vitals.pk).update(recorded_at=selected_datetime)

    return Response(patient_payload(patient, selected_date))
